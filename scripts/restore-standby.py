"""Restore one verified checkpoint to the dedicated empty loopback standby only."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--resume-setup', action='store_true', help='Resume only an untouched restore-drill organization')
    args = parser.parse_args()
    expected = json.loads((args.checkpoint / 'verification.json').read_bytes())
    token = (args.checkpoint / 'credentials/influx-operator-token').read_bytes().decode()
    runtime = '/opt/influxdb-2.7.12/influx'
    env = dict(os.environ, INFLUX_HOST='http://127.0.0.1:8086', INFLUX_TOKEN=token,
               INFLUX_CONFIGS_PATH='/tmp/standby-influx-config')
    env.pop('INFLUX_ORG', None)
    def cli(*cmd):
        p = subprocess.run([runtime, *cmd], env=env, capture_output=True, timeout=180)
        if p.returncode:
            message = p.stderr.decode(errors='replace').replace(token, '[redacted]')
            raise RuntimeError('Standby CLI failed: ' + message[:1000])
        return p.stdout
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(60):
        try:
            with opener.open('http://127.0.0.1:8086/api/v2/setup', timeout=2) as res:
                allowed = json.load(res)['allowed']
            break
        except OSError: time.sleep(1)
    else: raise RuntimeError('Standby startup timed out')
    if not allowed and not args.verify_only:
        if not args.resume_setup:
            raise RuntimeError('Refusing to overwrite an initialized server')
        organizations = json.loads(cli('org', 'list', '--json'))
        if len(organizations) != 1 or organizations[0]['name'] != 'restore-drill':
            raise RuntimeError('Resume is restricted to initial disposable setup metadata')
    import secrets
    payload = dict(username='restore-drill', password=secrets.token_urlsafe(32),
                   org='restore-drill', bucket='restore-drill', token=token)
    req = urllib.request.Request('http://127.0.0.1:8086/api/v2/setup',
        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    started = time.monotonic()
    if not args.verify_only:
        if allowed:
            with opener.open(req, timeout=15): pass
        cli('restore', '--full', str(args.checkpoint / 'backup'))
    env['INFLUX_ORG'] = 'home'
    buckets = json.loads(cli('bucket', 'list', '--org', 'home', '--json'))
    selected = sorted([dict(id=b['id'], name=b['name'], orgID=b['orgID'], retentionRules=b['retentionRules'])
                       for b in buckets], key=lambda b: b['id'])
    assert selected == expected['metadata']['buckets'], 'Bucket metadata differs'
    auths = json.loads(cli('auth', 'list', '--org', 'home', '--json'))
    selected_auth = sorted([dict(id=a['id'], description=a.get('description',''),
                                status=a['status'], permissions=a['permissions']) for a in auths], key=lambda a: a['id'])
    assert selected_auth == expected['metadata']['authorizations'], 'Authorization metadata differs'
    reader = next(a for a in auths if a.get('description','').startswith('grafana read-only'))
    env['INFLUX_TOKEN'] = reader['token']
    counts = {}
    for bucket in ('iot', 'network', 'voice_telemetry'):
        flux = 'from(bucket: ' + json.dumps(bucket) + ') |> range(start: 0) |> group() |> count()'
        counts[bucket] = cli('query', '--raw', flux).decode()
    report = dict(observed_at=datetime.now(timezone.utc).isoformat(),
        restore_and_queries_seconds=round(time.monotonic()-started,3), bucket_metadata_match=True,
        authorizations_match=True, grafana_read_token_verified=True, aggregate_query_results=counts,
        primary='unchanged', promotion='not performed')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
