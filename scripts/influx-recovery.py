"""Online InfluxDB 2.7.12 export and isolated full restore. No live cutover.

All Docker output is captured. Only allowlisted metadata and aggregate counts
leave this script. Disposable instances have no network, ports, host mounts or
production collectors. Secrets stay in protected, ignored data/ and secrets/.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'influxdb@sha256:b548ea6cdd265b4c28b305be5a93c4fc8b0d60583989598156895b80eefe29f4'


def command(args, input=None, timeout=300):
    result = subprocess.run(args, input=input, capture_output=True, timeout=timeout)
    if result.returncode:
        # Commands may return tokens, household data, or credential-bearing errors.
        raise RuntimeError('Command failed (%s), output withheld' % args[0])
    return result.stdout


def private_directory(path):
    path.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        user = command(['whoami']).decode().strip()
        command(['icacls', str(path), '/inheritance:r', '/grant:r',
                 user + ':(OI)(CI)F', 'SYSTEM:(OI)(CI)F'])
    else:
        path.chmod(0o700)


def live(command_text):
    return command(['docker', 'exec', 'iot-influxdb', 'sh', '-c',
                    'export INFLUX_TOKEN="$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN"; ' + command_text])


def summary(container, token_from_env=True):
    prefix = ('export INFLUX_TOKEN="$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN"; ' if token_from_env
              else 'export INFLUX_TOKEN="$(cat /tmp/recovery-token)"; ')
    def cli(args):
        return command(['docker', 'exec', container, 'sh', '-c', prefix + args])
    buckets = json.loads(cli('influx bucket list --org home --json'))
    auths = json.loads(cli('influx auth list --org home --json'))
    return {'buckets': sorted([{'id': b['id'], 'name': b['name'],
                'orgID': b['orgID'], 'retentionRules': b['retentionRules']}
                for b in buckets], key=lambda b: b['id']),
            'authorizations': sorted([{'id': a['id'], 'description': a.get('description', ''),
                'status': a['status'], 'permissions': a['permissions']} for a in auths],
                key=lambda a: a['id'])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Destination must be new')
    private_directory(args.out)
    private_directory(ROOT / 'secrets')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    remote = '/tmp/influx-recovery-' + stamp
    target = 'iot-restore-' + stamp.lower()
    started = time.monotonic()
    before = summary('iot-influxdb')
    token = live('printf %s "$INFLUX_TOKEN"')
    (ROOT / 'secrets/influx-operator-token').write_bytes(token)
    # Native backup API snapshots live shard state without stopping writers.
    live('umask 077; influx backup ' + remote)
    command(['docker', 'cp', 'iot-influxdb:' + remote, str(args.out / 'backup')])
    backup_seconds = time.monotonic() - started
    created = False
    try:
        command(['docker', 'run', '-d', '--name', target, '--network', 'none',
                 '--memory', '2g', '--cpus', '2', '--pids-limit', '256',
                 '--log-opt', 'max-size=5m', '--log-opt', 'max-file=2', IMAGE])
        created = True
        inspection = json.loads(command(['docker', 'inspect', target]))[0]
        assert inspection['HostConfig']['NetworkMode'] == 'none'
        assert not inspection['HostConfig']['PortBindings']
        assert not inspection['HostConfig']['Privileged']
        assert not inspection['HostConfig']['Binds']
        # Image-declared anonymous volumes are disposable; docker rm -v removes them.
        for _ in range(60):
            try:
                command(['docker', 'exec', target, 'curl', '-fsS', 'http://localhost:8086/health'])
                break
            except RuntimeError:
                time.sleep(1)
        else: raise RuntimeError('Isolated server startup timed out')
        setup = json.dumps(dict(username='restore-drill', password=secrets.token_urlsafe(32),
                     org='restore-drill', bucket='restore-drill', token=token.decode())).encode()
        command(['docker', 'exec', '-i', target, 'curl', '-fsS', '-X', 'POST',
                 'http://localhost:8086/api/v2/setup', '--data-binary', '@-'], setup)
        command(['docker', 'exec', '-i', target, 'sh', '-c',
                 'umask 077; cat > /tmp/recovery-token'], token)
        command(['docker', 'cp', str(args.out / 'backup'), target + ':/tmp/backup'])
        restore_start = time.monotonic()
        command(['docker', 'exec', target, 'sh', '-c',
                 'export INFLUX_TOKEN="$(cat /tmp/recovery-token)"; influx restore --full /tmp/backup'])
        after = summary(target, False)
        assert before == after, 'Bucket IDs/retentions or authorization metadata changed'
        # Count all retained rows per real bucket, then query again after restart.
        counts = {}
        for bucket in before['buckets']:
            if bucket['name'].startswith('_'): continue
            flux = ('from(bucket: ' + json.dumps(bucket['name']) + ') |> range(start: 0) '
                    '|> group() |> count()')
            command(['docker', 'exec', '-i', target, 'sh', '-c', 'cat > /tmp/check.flux'], flux.encode())
            raw = command(['docker', 'exec', target, 'sh', '-c',
                    'export INFLUX_TOKEN="$(cat /tmp/recovery-token)"; influx query --org home --raw --file /tmp/check.flux'])
            counts[bucket['name']] = raw.decode()
        restore_seconds = time.monotonic() - restore_start
        command(['docker', 'restart', target])
        for _ in range(60):
            try:
                assert summary(target, False) == before
                break
            except RuntimeError: time.sleep(1)
        else: raise RuntimeError('Restored server restart failed')
        report = dict(observed_at=datetime.now(timezone.utc).isoformat(), image=IMAGE,
                      backup_seconds=round(backup_seconds, 3), restore_and_query_seconds=round(restore_seconds, 3),
                      metadata_match=True, restart_verified=True, isolated=True,
                      metadata=before, aggregate_query_results=counts)
        (args.out / 'verification.json').write_bytes((json.dumps(report, indent=2)+'\n').encode())
        print(json.dumps(report, indent=2))
    finally:
        if created: command(['docker', 'rm', '-f', '-v', target])
    # This exact script-created temporary export is safe to remove after read-back.
    live('rm -rf -- ' + remote)


if __name__ == '__main__': main()
