"""Bounded credential restore drill for an encrypted checkpoint.

Restores only the two *-infra-token.json handoff files from the checkpoint's
restic repository inside a disposable --network none container, copies them to
a fresh private directory under data/, and sends each token through the same
harmless probe tools/provision_infra.py uses (write: empty body, 400 expected;
read: bucket list limit=1, 200 expected). Nothing is written to InfluxDB.

Prints only label, auth_id, description and probe_ok per file plus the
checkpoint path and snapshot id. Every print goes through a guard that refuses
any string containing a restored token. The temporary directory and container
are removed in finally. Exit status 1 on any failure.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import secrets
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('provision_infra', ROOT / 'tools/provision_infra.py')
pi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pi)
r = pi.recovery  # scripts/influx-recovery.py: command(), live(), private_directory()

IMAGE = 'threadripper-validation'
KEY = r.ROOT / 'secrets/influx-restic-password'
DATA = r.ROOT / 'data'
INCLUDE = '/checkpoint/credentials/*-infra-token.json'
# label -> probe kind; matches CREDENTIALS in scripts/encrypt-checkpoint.py
CREDENTIALS = {'threadripper-infra-token.json': 'write', 'grafana-infra-token.json': 'read'}

_loaded_tokens = set()


def emit(text):
    """The only output path. Raises instead of printing a restored token."""
    for token in _loaded_tokens:
        if token and token in text:
            raise RuntimeError('Refusing to print output that contains a restored token')
    print(text)


def probe(label, path, org_name, org_id, bucket_id):
    saved = json.loads(path.read_bytes().decode())
    token = saved.get('token')
    if isinstance(token, str) and token: _loaded_tokens.add(token)
    ok = pi.probe_saved_token(CREDENTIALS[label], org_name, org_id, bucket_id, token)
    return dict(label=label, auth_id=saved.get('auth_id'),
                description=saved.get('description'), probe_ok=bool(ok))


def live_ids(org_name, bucket_name):
    orgs = json.loads(r.live('influx org list --json'))
    buckets = json.loads(r.live('influx bucket list --org %s --json' % org_name))
    org_id = pi.validate_id('org id', pi.find_org(orgs, org_name)['id'])
    bucket_id = pi.validate_id('bucket id', pi.require_bucket(buckets, bucket_name)['id'])
    return org_id, bucket_id


def drill(checkpoint, org_name, bucket_name):
    repository = checkpoint / 'repository'
    if not repository.is_dir(): raise ValueError('Checkpoint has no repository/ directory')
    if not KEY.is_file(): raise ValueError('Restic password file missing')
    org_id, bucket_id = live_ids(org_name, bucket_name)
    name = 'iot-credential-drill-' + secrets.token_hex(4)
    temp = DATA / name
    if temp.exists(): raise ValueError('Temporary directory already exists')
    created = False
    try:
        r.private_directory(temp)
        r.command(['docker', 'run', '-d', '--name', name, '--network', 'none', '--memory', '512m',
                   '--cpus', '1', '--entrypoint', 'sleep', IMAGE, '900'])
        created = True
        inspection = json.loads(r.command(['docker', 'inspect', name]))[0]
        assert inspection['HostConfig']['NetworkMode'] == 'none'
        assert not inspection['HostConfig']['Binds']
        r.command(['docker', 'cp', str(repository), name + ':/repository'])
        r.command(['docker', 'cp', str(KEY), name + ':/password'])
        r.command(['docker', 'exec', name, 'sh', '-c',
            'export RESTIC_REPOSITORY=/repository RESTIC_PASSWORD_FILE=/password; '
            'restic check && restic restore latest --target /restore --verify --include "%s"' % INCLUDE])
        snapshots = json.loads(r.command(['docker', 'exec', name, 'restic', '-r', '/repository',
                                          '--password-file', '/password', 'snapshots', '--json']))
        r.command(['docker', 'cp', name + ':/restore/checkpoint/credentials', str(temp / 'credentials')])
        results = []
        for label in CREDENTIALS:
            path = temp / 'credentials' / label
            if path.is_file():
                results.append(probe(label, path, org_name, org_id, bucket_id))
            else:
                results.append(dict(label=label, auth_id=None, description=None, probe_ok=False,
                                    note='not in snapshot'))
        return dict(checkpoint=str(checkpoint), snapshot=snapshots[-1]['id'], credentials=results,
                    ok=all(c['probe_ok'] for c in results))
    finally:
        try:
            if created: r.command(['docker', 'rm', '-f', '-v', name])
        finally:
            shutil.rmtree(temp, ignore_errors=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--org', default=pi.DEFAULT_ORG)
    p.add_argument('--bucket', default=pi.DEFAULT_BUCKET)
    args = p.parse_args(argv)
    pi.validate_name('--org', args.org)
    pi.validate_name('--bucket', args.bucket)
    try:
        report = drill(args.checkpoint, args.org, args.bucket)
    except Exception as exc:
        emit(json.dumps(dict(ok=False, error=exc.__class__.__name__, detail=str(exc))))
        return 1
    emit(json.dumps(report, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__': sys.exit(main())
