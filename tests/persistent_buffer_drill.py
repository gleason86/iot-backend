"""Synthetic 1.32.3 disk-buffer recovery across collector replacement.

No production mounts, credentials, endpoints or published ports. The disposable
named volume holds ten fixed records; this is not a physical host-loss test.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import time
from continuity_drill import IMAGE, TOKEN, cmd, setup, ids, wait_ids

TELEGRAF = 'sha256:f437048e98b284ff5f98f34dd51cb250cf187852c0792673aadddb1e00ac7b2b'


def main():
    prefix = 'persistent-buffer-' + secrets.token_hex(4)
    network, volume, database, collector = [prefix + '-' + x for x in ('net', 'queue', 'db', 'collector')]
    made = []
    cmd(['docker', 'network', 'create', '--internal', network])
    try:
        cmd(['docker', 'volume', 'create', volume])
        cmd(['docker', 'run', '-d', '--name', database, '--network', network,
             '--memory', '1g', '--cpus', '1', IMAGE])
        made.append(database)
        setup(database)
        config = f'''[agent]
interval="1s"
flush_interval="1s"
metric_batch_size=1
metric_buffer_limit=3
buffer_strategy="disk"
buffer_directory="/queue"
omit_hostname=true
debug=true
[[inputs.exec]]
commands=["cat /tmp/record"]
data_format="influx"
[[outputs.influxdb_v2]]
alias="stable-drill-output"
urls=["http://{database}:8086"]
token="{TOKEN}"
organization="drill"
bucket="drill"
timeout="1s"
'''.encode()

        def create(records):
            cmd(['docker', 'run', '-d', '--name', collector, '--network', 'none',
                 '--memory', '256m', '--cpus', '1', '--log-opt', 'max-size=2m',
                 '--mount', 'type=volume,src=' + volume + ',dst=/queue',
                 '--entrypoint', 'sh', TELEGRAF, '-c',
                 'while test ! -f /tmp/start; do sleep 1; done; exec telegraf --config /tmp/drill.conf'])
            made.append(collector)
            cmd(['docker', 'exec', '-i', collector, 'sh', '-c', 'cat > /tmp/drill.conf'], config)
            cmd(['docker', 'exec', '-i', collector, 'sh', '-c', 'cat > /tmp/record'], records)
            cmd(['docker', 'exec', collector, 'touch', '/tmp/start'])

        records = ('\n'.join('continuity,id=%d value=%di %d' % (i, i, 1789110000000000000+i)
                             for i in range(31, 41)) + '\n').encode()
        create(records)
        time.sleep(5)
        cmd(['docker', 'exec', collector, 'sh', '-c', ': > /tmp/record'])
        queued_bytes = int(cmd(['docker', 'exec', collector, 'du', '-sb', '/queue']).decode().split()[0])
        assert queued_bytes > 4096, 'No disk queue observed'
        assert ids(database) == [], 'Isolated collector unexpectedly delivered'
        cmd(['docker', 'kill', collector])
        cmd(['docker', 'rm', '-v', collector]); made.remove(collector)
        create(b'')  # Fresh container has no source records; only queue volume survives.
        time.sleep(3)
        cmd(['docker', 'network', 'disconnect', 'none', collector])
        cmd(['docker', 'network', 'connect', network, collector])
        replay_seconds = wait_ids(database, list(range(31, 41)), 30)
        time.sleep(2)
        assert ids(database) == list(range(31, 41))
        report = dict(observed_at=datetime.now(timezone.utc).isoformat(), image=TELEGRAF,
                      sigkill_and_container_replacement=True, queue_bytes=queued_bytes,
                      source_records_on_replacement=0, recovered_field_rows=10,
                      configured_metric_buffer_limit=3, more_than_limit_recovered=True,
                      replay_seconds=replay_seconds, physical_host_loss=False,
                      limits='Fixed timestamps deduplicate repeated input samples in Influx; transport exactly-once is not proven. Disk growth is not bounded by the metric limit; production disk-full/power-loss testing is still required.')
        out = Path(__file__).resolve().parents[1] / 'data/persistent-buffer-drill.json'
        out.parent.mkdir(exist_ok=True)
        out.write_bytes((json.dumps(report, indent=2)+'\n').encode())
        print(json.dumps(report, indent=2))
    finally:
        for name in reversed(made): cmd(['docker', 'rm', '-f', '-v', name])
        cmd(['docker', 'volume', 'rm', volume])
        cmd(['docker', 'network', 'rm', network])


if __name__ == '__main__': main()
