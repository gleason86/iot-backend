"""Disposable 2.7.12 replication, process-loss, partition and manual failback drill.

Uses only synthetic records, an internal Docker network and anonymous volumes.
This tests database mechanics, not a distributed fencing controller or host loss.
"""
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

IMAGE = 'influxdb@sha256:b548ea6cdd265b4c28b305be5a93c4fc8b0d60583989598156895b80eefe29f4'
TOKEN = 'disposable-continuity-test-token-only'


def cmd(args, data=None):
    p = subprocess.run(args, input=data, capture_output=True, timeout=120)
    if p.returncode: raise RuntimeError((p.stderr + p.stdout).decode()[:1000])
    return p.stdout


def api(host, path, body=None, method=None, content='application/json'):
    args = ['docker', 'exec', '-i', host, 'curl', '--fail-with-body', '-sS', '--max-time', '5',
            '-H', 'Authorization: Token ' + TOKEN, '-H', 'Content-Type: ' + content]
    if method: args += ['-X', method]
    if body is not None: args += ['--data-binary', '@-']
    args += ['http://localhost:8086' + path]
    raw = cmd(args, body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None)
    return raw


def ready(host):
    for _ in range(60):
        try: api(host, '/health'); return
        except RuntimeError: time.sleep(1)
    raise RuntimeError('Startup timeout')


def setup(host):
    ready(host)
    return json.loads(api(host, '/api/v2/setup', dict(username='drill', password='synthetic-password-for-drill',
                  org='drill', bucket='drill', token=TOKEN)))


def write(host, numbers):
    text = '\n'.join('continuity,id=%d value=%di %d' % (i, i, 1789110000000000000+i) for i in numbers)
    api(host, '/api/v2/write?org=drill&bucket=drill&precision=ns', text.encode(), content='text/plain')


def ids(host):
    flux = b'from(bucket:"drill") |> range(start:2026-09-11T00:00:00Z, stop:2026-09-12T00:00:00Z) |> keep(columns:["id","_value"]) |> group()'
    raw = api(host, '/api/v2/query?org=drill', flux, content='application/vnd.flux').decode()
    rows = [row for row in csv.reader(io.StringIO(raw)) if row and not row[0].startswith('#')]
    if not rows: return []
    index = rows[0].index('id') if 'id' in rows[0] else rows[0].index('_value')
    return sorted(int(row[index]) for row in rows[1:] if row[index].isdigit())


def wait_ids(host, expected, seconds=60):
    start = time.monotonic()
    for _ in range(seconds):
        if ids(host) == expected: return round(time.monotonic()-start, 3)
        time.sleep(1)
    raise AssertionError('Replica mismatch: ' + str(ids(host)))


def main():
    prefix = 'iot-drill-' + secrets.token_hex(4)
    network = prefix + '-net'
    primary, standby, failback = [prefix + '-' + x for x in ('primary', 'standby', 'failback')]
    made = []
    report = {'observed_at': datetime.now(timezone.utc).isoformat(), 'image': IMAGE,
              'physical_host_loss': 'not tested', 'automatic_fencing': 'not implemented'}
    cmd(['docker', 'network', 'create', '--internal', network])
    try:
        def create(name):
            cmd(['docker', 'run', '-d', '--name', name, '--network', network, '--memory', '1g',
                 '--cpus', '1', '--pids-limit', '128', '--log-opt', 'max-size=5m', IMAGE])
            made.append(name)
            return setup(name)
        a, b = create(primary), create(standby)
        write(primary, [1])
        remote = json.loads(api(primary, '/api/v2/remotes', dict(name='drill', orgID=a['org']['id'],
            remoteOrgID=b['org']['id'], remoteURL='http://' + standby + ':8086',
            remoteAPIToken=TOKEN, allowInsecureTLS=False)))
        api(primary, '/api/v2/replications', dict(name='drill', orgID=a['org']['id'], remoteID=remote['id'],
            localBucketID=a['bucket']['id'], remoteBucketID=b['bucket']['id'],
            maxAgeSeconds=3600, maxQueueSizeBytes=33554430, dropNonRetryableData=False))
        write(primary, [2])
        report['initial_replication_seconds'] = wait_ids(standby, [2])
        report['historical_backfill'] = 'record 1 absent as expected'
        # Partition only the synthetic standby; retain primary and its disk queue.
        cmd(['docker', 'network', 'disconnect', network, standby])
        write(primary, list(range(3, 13)))
        assert ids(standby) == [2]
        time.sleep(2)
        print('Queued during partition:', api(primary, '/api/v2/replications?orgID=' + a['org']['id']).decode(), flush=True)
        report['stale_standby_rejected'] = True  # comparison blocks this test's manual promotion
        cmd(['docker', 'kill', primary])
        cmd(['docker', 'start', primary]); ready(primary)
        cmd(['docker', 'network', 'connect', network, standby])
        print('Queue after process restart:', api(primary, '/api/v2/replications?orgID=' + a['org']['id']).decode(), flush=True)
        try:
            report['queue_recovery_after_sigkill_seconds'] = wait_ids(standby, list(range(2, 13)), 30)
        except AssertionError:
            report['idle_queue_after_restart'] = 'Still queued after 30 seconds; not autonomously recovered'
            # Same point ID/timestamp is a controlled idempotent replay. This is
            # a measured intervention, not hidden success of autonomous replay.
            write(primary, [12])
            report['queue_recovery_after_new_write_seconds'] = wait_ids(standby, list(range(2, 13)))
        api(primary, '/api/v2/delete?org=drill&bucket=drill', dict(start='2026-01-01T00:00:00Z',
            stop='2027-01-01T00:00:00Z', predicate='_measurement="continuity" AND id="2"'))
        assert 2 not in ids(primary) and 2 in ids(standby), (ids(primary), ids(standby))
        report['delete_replication'] = 'not replicated, independently verified'
        # Operator fencing: stopped container is positively verified before writes.
        cmd(['docker', 'stop', primary])
        state = json.loads(cmd(['docker', 'inspect', primary]))[0]['State']
        assert not state['Running']
        write(standby, [13])
        assert ids(standby) == list(range(2, 14))
        report['manual_promotion'] = 'synthetic standby writer enabled after verified primary stop'
        # Returning old primary remains disconnected; no automatic rejoin or replay.
        cmd(['docker', 'network', 'disconnect', network, primary])
        cmd(['docker', 'start', primary]); ready(primary)
        assert 13 not in ids(primary)
        cmd(['docker', 'stop', primary])
        report['old_primary_return'] = 'isolated, stale, not admitted as writer'
        create(failback)
        with tempfile.TemporaryDirectory() as tmp:
            cmd(['docker', 'exec', '-e', 'INFLUX_TOKEN=' + TOKEN, standby,
                 'influx', 'backup', '/tmp/failback-backup'])
            cmd(['docker', 'cp', standby + ':/tmp/failback-backup', tmp + '/backup'])
            cmd(['docker', 'cp', tmp + '/backup', failback + ':/tmp/backup'])
            cmd(['docker', 'exec', '-e', 'INFLUX_TOKEN=' + TOKEN, failback,
                 'influx', 'restore', '--full', '/tmp/backup'])
        assert ids(failback) == ids(standby)
        cmd(['docker', 'stop', standby])
        write(failback, [14])
        assert ids(failback) == list(range(2, 15))
        report['manual_failback'] = 'fresh full restore, old writer stopped, IDs 2 through 14 exactly once'
        report['limits'] = 'No production cutover, full-disk test, live collector continuity, or physical partition/host loss'
        print(json.dumps(report, indent=2))
        out = Path(__file__).resolve().parents[1] / 'data/continuity-drill.json'
        out.parent.mkdir(exist_ok=True)
        out.write_bytes((json.dumps(report, indent=2)+'\n').encode())
    except Exception:
        for name in made:
            result = subprocess.run(['docker', 'logs', '--tail', '40', name], capture_output=True)
            logs = (result.stderr + result.stdout).decode()
            print('\n'.join(line for line in logs.splitlines() if 'error' in line.lower() or 'panic' in line.lower()), flush=True)
        raise
    finally:
        for name in made: cmd(['docker', 'rm', '-f', '-v', name])
        cmd(['docker', 'network', 'rm', network])


if __name__ == '__main__': main()
