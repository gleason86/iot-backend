"""Actual disposable Telegraf overflow/process loss and InfluxDB ENOSPC checks."""
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import subprocess
import time
from continuity_drill import IMAGE, cmd, setup, write, ids, ready

IMAGES = [
    ('iot-1.29.5', 'sha256:c3b08145370a7e8d0614ad8b883a14b7003bfa505be6d31023d75200e935e7d6'),
    ('network-1.32.3', 'sha256:f437048e98b284ff5f98f34dd51cb250cf187852c0792673aadddb1e00ac7b2b'),
]


def logs(name, since=None):
    args = ['docker', 'logs'] + (['--since', since] if since else []) + [name]
    p = subprocess.run(args, capture_output=True)
    return (p.stdout + p.stderr).decode()


def main():
    report = {'observed_at': datetime.now(timezone.utc).isoformat(), 'telegraf': {}}
    for label, image in IMAGES:
        name = 'buffer-drill-' + secrets.token_hex(4)
        cmd(['docker', 'run', '-d', '--name', name, '--network', 'none', '--memory', '256m',
             '--entrypoint', 'sh', image, '-c', 'while test ! -f /tmp/start; do sleep 1; done; exec telegraf --config /tmp/drill.conf'])
        try:
            config = b'''[agent]
interval="1s"
flush_interval="1s"
metric_batch_size=1
metric_buffer_limit=3
debug=true
[[inputs.exec]]
commands=["cat /tmp/record"]
data_format="influx"
[[outputs.influxdb_v2]]
urls=["http://127.0.0.1:9"]
token="disposable"
organization="drill"
bucket="drill"
timeout="1s"
'''
            cmd(['docker', 'exec', '-i', name, 'sh', '-c', 'cat > /tmp/drill.conf'], config)
            cmd(['docker', 'exec', '-i', name, 'sh', '-c', 'cat > /tmp/record'], b'buffer_fixture value=1i\n')
            cmd(['docker', 'exec', name, 'touch', '/tmp/start'])
            time.sleep(9)
            before = logs(name)
            assert 'buffer overflow' in before.lower(), before[-1000:]
            cmd(['docker', 'exec', name, 'sh', '-c', ': > /tmp/record'])
            cmd(['docker', 'kill', name])
            since = datetime.now(timezone.utc).isoformat()
            cmd(['docker', 'start', name]); time.sleep(4)
            after = logs(name, since)
            assert 'Buffer fullness: 0 / 3 metrics' in after, after[-1000:]
            report['telegraf'][label] = dict(overflow_observed=True, queue_empty_after_sigkill=True,
                durable_queue=False, fixture_capacity=3, real_config_capacity=10000 if label.startswith('iot') else 20000)
        finally: cmd(['docker', 'rm', '-f', '-v', name])
    name = 'disk-drill-' + secrets.token_hex(4)
    cmd(['docker', 'run', '-d', '--name', name, '--network', 'none', '--memory', '1g',
         '--tmpfs', '/var/lib/influxdb2:rw,size=64m', '--entrypoint', 'sh', IMAGE, '-c',
         'while true; do influxd --bolt-path /var/lib/influxdb2/influxd.bolt --engine-path /var/lib/influxdb2/engine --sqlite-path /var/lib/influxdb2/influxd.sqlite --reporting-disabled & echo $! > /tmp/influxd.pid; wait $!; sleep 1; done'])
    try:
        setup(name)
        fill = subprocess.run(['docker', 'exec', name, 'sh', '-c',
            'dd if=/dev/zero of=/var/lib/influxdb2/drill-fill bs=1M count=128'], capture_output=True)
        assert fill.returncode != 0 and b'No space left' in fill.stderr
        rejected = False
        try: write(name, [21])
        except RuntimeError: rejected = True
        assert rejected, 'Influx unexpectedly acknowledged the full-filesystem write'
        cmd(['docker', 'exec', name, 'rm', '/var/lib/influxdb2/drill-fill'])
        needs_restart = False
        try: write(name, [21])
        except RuntimeError:
            needs_restart = True
            # Restart only influxd, preserving this container's tmpfs contents.
            cmd(['docker', 'exec', name, 'sh', '-c', 'kill -TERM "$(cat /tmp/influxd.pid)"'])
            time.sleep(2); ready(name)
            write(name, [21])
        assert ids(name) == [21]
        report['influx_full_disk'] = dict(filesystem='disposable 64 MiB tmpfs, not host SSD',
            enospc_observed=True, write_rejected=True, process_restart_required=needs_restart,
            retry_after_free_space_and_recovery=True, final_rows=1)
    finally: cmd(['docker', 'rm', '-f', '-v', name])
    out = Path(__file__).resolve().parents[1] / 'data/buffer-disk-drill.json'
    out.write_bytes((json.dumps(report, indent=2)+'\n').encode())
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
