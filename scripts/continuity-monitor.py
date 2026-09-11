"""Read-only backend/producer freshness monitor. Never promotes or sends messages."""
import argparse
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import urllib.request

THRESHOLDS = {'iot:W': 900, 'network:cable_modem': 1020, 'network:wifi_ap': 1020,
              'network:starlink_dish': 300, 'network:orbi_unit': 300,
              'network:router_wan': 300, 'network:router_port': 300, 'network:router_system': 300}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Monitoring endpoint redirects are not allowed')


def transition(previous, failures, now):
    bad = bool(failures)
    count = previous.get('consecutive', 0) + 1 if previous.get('last_bad') == bad else 1
    status = previous.get('status', 'unknown')
    if count >= 3: status = 'failed' if bad else 'healthy'
    return dict(observed_at=now.isoformat(), status=status, last_bad=bad, consecutive=count,
                failures=failures, transition_at=now.isoformat() if status != previous.get('status')
                else previous.get('transition_at'), promotion='disabled', notifications='not configured')


def query(config, bucket):
    # Only source watermarks leave InfluxDB; no household values are retrieved.
    names = [key.split(':', 1)[1] for key in THRESHOLDS if key.startswith(bucket + ':')]
    flux = ('from(bucket:' + json.dumps(bucket) + ') |> range(start:-1h) '
            '|> filter(fn:(r)=>contains(value:r._measurement,set:' + json.dumps(names) + ')) '
            '|> group(columns:["_measurement"]) |> max(column:"_time") '
            '|> keep(columns:["_measurement","_time"])')
    req = urllib.request.Request(config['url'] + '/api/v2/query?org=home', data=flux.encode(),
          headers={'Authorization': 'Token ' + config['token'], 'Content-Type': 'application/vnd.flux'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=10) as res: raw = res.read(100001)
    if len(raw) > 100000: raise ValueError('Unexpected query size')
    values = {}
    header = None
    for row in csv.reader(io.StringIO(raw.decode())):
        if not row or row[0].startswith('#'): continue
        if '_measurement' in row and '_time' in row:
            header = row; continue
        if header:
            data = dict(zip(header, row))
            values[bucket + ':' + data['_measurement']] = data['_time']
    return values


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--state', type=Path, required=True)
    args = p.parse_args()
    config = json.loads(args.config.read_bytes())
    # Fixed intended LAN endpoint; this is not a general HTTP credential forwarder.
    if config['url'] != 'http://192.168.1.100:8086': raise ValueError('Unreviewed endpoint')
    now = datetime.now(timezone.utc)
    previous = json.loads(args.state.read_bytes()) if args.state.exists() else {}
    try:
        values = {**query(config, 'iot'), **query(config, 'network')}
        failures = []
        for key, seconds in THRESHOLDS.items():
            stamp = values.get(key)
            age = (now - datetime.fromisoformat(stamp.replace('Z', '+00:00'))).total_seconds() if stamp else None
            if age is None or age > seconds or age < -60:
                failures.append(dict(producer=key, reason='missing-or-stale', age_seconds=age))
    except Exception as exc:
        values = {}
        failures = [dict(producer='backend', reason=type(exc).__name__)]
    state = transition(previous, failures, now)
    state['watermarks'] = values
    args.state.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.state.with_suffix('.tmp')
    with temporary.open('wb') as stream:
        stream.write((json.dumps(state, indent=2)+'\n').encode()); stream.flush(); os.fsync(stream.fileno())
    temporary.replace(args.state)
    print(json.dumps(state))
    return 1 if state['status'] == 'failed' else 0


if __name__ == '__main__': raise SystemExit(main())
