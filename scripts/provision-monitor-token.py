"""Create/reuse one narrowly scoped backend-reader identity; never print its token."""
import importlib.util
import json
from pathlib import Path
spec = importlib.util.spec_from_file_location('recovery', Path(__file__).with_name('influx-recovery.py'))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
description = 'threadripper continuity monitor read-only iot and network'
expected = {'read:orgs/714f34e4c62e3500/buckets/dc846c7b25ee1436',
            'read:orgs/714f34e4c62e3500/buckets/57497837fc976b6f'}
rows = json.loads(r.live('influx auth list --org home --json'))
matches = [row for row in rows if row.get('description') == description]
if not matches:
    row = json.loads(r.live('influx auth create --org home --read-bucket dc846c7b25ee1436 '
           '--read-bucket 57497837fc976b6f --description "' + description + '" --json'))
    matches = row if isinstance(row, list) else [row]
assert len(matches) == 1 and matches[0]['status'] == 'active'
assert set(matches[0]['permissions']) == expected
r.private_directory(r.ROOT / 'secrets')
(r.ROOT / 'secrets/continuity-monitor.json').write_bytes((json.dumps(dict(
    url='http://192.168.1.100:8086', token=matches[0]['token']))+'\n').encode())
print('Dedicated read-only monitor credential stored in ignored secrets/continuity-monitor.json')
