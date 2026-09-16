"""Idempotent provisioning for the InfluxDB `infra` bucket and its dedicated
Threadripper write-only token, plus a consolidated Grafana read-only token
(read:iot,network,voice_telemetry,infra) that will eventually replace the
existing shared Grafana datasource credential. Dry-run (plan-only) unless
`--apply` is passed. Never prints or logs a token value; new tokens are
persisted only to ACL-protected files under ignored `secrets/`.

The existing shared Grafana token is validated but never modified or
revoked: it stays active so the datasource swap (this repo does not own
Grafana's .env) can be rolled back. See
docs/infra-monitoring-2026-09-15.md for the full design and handoff.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery', ROOT / 'scripts/influx-recovery.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)

DEFAULT_ORG = 'home'
DEFAULT_BUCKET = 'infra'
DEFAULT_RETENTION_DAYS = 30
INFLUX_URL = 'http://10.77.77.1:8086'
# Probes run inside the existing InfluxDB container, not over a host LAN route.
PROBE_URL = 'http://127.0.0.1:8086'
NAME_PATTERN = re.compile(r'[A-Za-z0-9_-]+')
ID_PATTERN = re.compile(r'[0-9a-fA-F]{16}')

# Buckets the existing shared Grafana datasource token already reads. The
# consolidated replacement token must cover exactly these plus the new bucket.
ORIGINAL_GRAFANA_BUCKETS = ('iot', 'network', 'voice_telemetry')
GRAFANA_SOURCE_DESCRIPTION = 'grafana read-only (iot, network, voice_telemetry)'

WRITE_SECRET_PATH = ROOT / 'secrets/threadripper-infra-token.json'
GRAFANA_SECRET_PATH = ROOT / 'secrets/grafana-infra-token.json'


def validate_id(label, value):
    if not ID_PATTERN.fullmatch(value):
        raise RuntimeError(f'{label} {value!r} does not look like a valid InfluxDB id; refusing to use it')
    return value


def validate_name(flag, value):
    if not NAME_PATTERN.fullmatch(value):
        raise ValueError(f'{flag} must be alphanumeric/-/_ only, got {value!r}')


def find_org(orgs, name):
    matches = [o for o in orgs if o['name'] == name]
    if not matches:
        raise RuntimeError(f'Org {name!r} not found')
    return matches[0]


def find_bucket(buckets, name):
    matches = [b for b in buckets if b['name'] == name]
    return matches[0] if matches else None


def require_bucket(buckets, name):
    bucket = find_bucket(buckets, name)
    if bucket is None:
        raise RuntimeError(f'Bucket {name!r} not found; required to validate/consolidate Grafana read scope')
    return bucket


def expected_permissions(kind, org_id, bucket_ids):
    return {f'{kind}:orgs/{org_id}/buckets/{bid}' for bid in bucket_ids}


def plan_bucket(buckets, bucket_name, retention_days):
    existing = find_bucket(buckets, bucket_name)
    if existing is None:
        return {'action': 'create', 'bucket': bucket_name, 'retention_days': retention_days}
    expected_seconds = retention_days * 86400
    rules = existing.get('retentionRules') or []
    actual_seconds = rules[0]['everySeconds'] if rules else 0
    if actual_seconds != expected_seconds:
        raise RuntimeError(
            f'Bucket {bucket_name!r} already exists with retention {actual_seconds}s, '
            f'expected {expected_seconds}s; refusing to modify an existing bucket automatically')
    return {'action': 'skip', 'bucket': bucket_name, 'id': validate_id('bucket id', existing['id']),
            'reason': 'already provisioned'}


def find_source_grafana_auth(auths, org_id, source_bucket_ids):
    """Validate the existing shared Grafana token has exactly the expected
    read scope before any consolidated replacement is planned. Fails loudly
    on an unexpected scope or an ambiguous/missing source; never mutated."""
    matches = [a for a in auths if a.get('description') == GRAFANA_SOURCE_DESCRIPTION]
    if not matches:
        raise RuntimeError(
            f'No existing token with description {GRAFANA_SOURCE_DESCRIPTION!r} found; '
            'ambiguous source for the consolidated Grafana credential, refusing to guess')
    if len(matches) > 1:
        raise RuntimeError(
            f'Multiple tokens with description {GRAFANA_SOURCE_DESCRIPTION!r}; ambiguous '
            'source for the consolidated Grafana credential, refusing')
    source = matches[0]
    if source['status'] != 'active':
        raise RuntimeError(f'Source Grafana token is not active ({source["status"]!r}); needs manual review')
    expected = expected_permissions('read', org_id, source_bucket_ids)
    if set(source['permissions']) != expected:
        raise RuntimeError(
            f'Source Grafana token has unexpected scopes {sorted(source["permissions"])}, '
            f'expected exactly {sorted(expected)}; refusing to build a consolidated token from it')
    return source


def grafana_token_description(bucket_name):
    return f'grafana read-only ({", ".join(ORIGINAL_GRAFANA_BUCKETS + (bucket_name,))})'


def probe_saved_token(kind, org_name, org_id, bucket_id, token):
    """Harmless authenticated request confirming a saved token is still
    usable. Never writes data and never logs the token value; only an HTTP
    status code crosses back out of the container."""
    validate_id('org id', org_id)
    validate_id('bucket id', bucket_id)
    validate_name('org name', org_name)
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_+=/-]+', token):
        return False
    if kind == 'write':
        url = f'{PROBE_URL}/api/v2/write?org={org_name}&bucket={bucket_id}'
        # Empty body: a valid token gets a 400 (bad request body), an invalid
        # one gets 401/403. No point is ever written either way.
        extra = ['--request', 'POST', '--data-binary', '']
        ok_codes = {'204', '400'}
    else:
        url = f'{PROBE_URL}/api/v2/buckets?orgID={org_id}&limit=1'
        extra = []
        ok_codes = {'200'}
    # curl reads its credential-bearing config from stdin; neither the host nor
    # container process arguments contain the token. Bound every network probe.
    config = f'url = "{url}"\nheader = "Authorization: Token {token}"\n'
    out = recovery.command(['docker', 'exec', '-i', 'iot-influxdb', 'curl',
                            '--silent', '--max-time', '10', '--output', '/dev/null',
                            '--write-out', '%{http_code}', '--config', '-'] + extra,
                           input=config.encode(), timeout=20)
    return out.decode().strip() in ok_codes


def verify_local_credential(secret_path, auth_id, kind, org_name, org_id, bucket_id):
    """An existing active, correctly scoped auth is only safe to treat as
    already-provisioned if we also hold a working local copy of its secret
    (Influx never lets it be re-read). Missing/stale/broken credentials fail
    clearly instead of silently skipping or rotating."""
    if not secret_path.exists():
        raise RuntimeError(
            f'Existing active token (id {auth_id}) has no local credential file at '
            f'{secret_path}; cannot verify it is usable. Refusing to silently skip or '
            'rotate -- token secrets cannot be re-read from Influx, this needs manual '
            'reconciliation before any provisioning can proceed.')
    try:
        saved = json.loads(secret_path.read_text())
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f'Local credential file at {secret_path} is unreadable/corrupt '
            f'({exc.__class__.__name__}); refusing to treat the existing token as provisioned'
        ) from None
    if saved.get('auth_id') != auth_id:
        raise RuntimeError(
            f'Local credential file at {secret_path} is for a different token id '
            f'({saved.get("auth_id")!r}) than the existing live token ({auth_id!r}); refusing to skip')
    token = saved.get('token')
    if not token:
        raise RuntimeError(f'Local credential file at {secret_path} has no token value; refusing to skip')
    if not probe_saved_token(kind, org_name, org_id, bucket_id, token):
        raise RuntimeError(
            f'Saved credential for token id {auth_id} failed a harmless authenticated probe; '
            'it may have been revoked or corrupted. Refusing to silently skip or rotate -- '
            'this needs manual reconciliation.')


def _plan_token(auths, description, kind, org_name, org_id, bucket_id, permission_bucket_ids, secret_path):
    matches = [a for a in auths if a.get('description') == description]
    if not matches:
        return {'action': 'create', 'description': description}
    if len(matches) > 1:
        raise RuntimeError(f'Multiple existing tokens with description {description!r}; ambiguous, refusing')
    match = matches[0]
    if bucket_id is None:
        raise RuntimeError(
            f'Token {description!r} already exists (id {match["id"]}) but its target bucket '
            'does not exist yet; inconsistent state, refusing to plan blindly')
    if match['status'] != 'active':
        raise RuntimeError(f'Existing token {description!r} is not active ({match["status"]!r}); needs manual review')
    expected = expected_permissions(kind, org_id, permission_bucket_ids)
    if set(match['permissions']) != expected:
        raise RuntimeError(
            f'Existing token {description!r} has unexpected permissions {sorted(match["permissions"])}, '
            f'expected exactly {sorted(expected)}; refusing to treat as already provisioned')
    verify_local_credential(secret_path, match['id'], kind, org_name, org_id, bucket_id)
    return {'action': 'skip', 'description': description, 'id': match['id'],
            'reason': 'already provisioned; local credential verified usable'}


def build_plan(orgs, buckets, auths, org_name, bucket_name, retention_days):
    org = find_org(orgs, org_name)
    org_id = validate_id('org id', org['id'])

    source_bucket_ids = [validate_id('bucket id', require_bucket(buckets, name)['id'])
                          for name in ORIGINAL_GRAFANA_BUCKETS]
    # Validate the source token's scope first, before any other planning.
    find_source_grafana_auth(auths, org_id, source_bucket_ids)

    bucket_step = plan_bucket(buckets, bucket_name, retention_days)
    new_bucket_id = bucket_step.get('id')

    write_description = f'threadripper {bucket_name} write-only, {bucket_name} bucket'
    write_step = _plan_token(
        auths, write_description, 'write', org_name, org_id, new_bucket_id,
        [new_bucket_id] if new_bucket_id else [], WRITE_SECRET_PATH)

    grafana_description = grafana_token_description(bucket_name)
    grafana_bucket_ids = source_bucket_ids + ([new_bucket_id] if new_bucket_id else [])
    grafana_step = _plan_token(
        auths, grafana_description, 'read', org_name, org_id, new_bucket_id,
        grafana_bucket_ids, GRAFANA_SECRET_PATH)

    # Detect incomplete/foreign local state before even creating the bucket.
    for step, path in ((write_step, WRITE_SECRET_PATH), (grafana_step, GRAFANA_SECRET_PATH)):
        if step['action'] == 'create':
            preflight_secret_path(path)

    return {
        'org': org['name'],
        'org_id': org_id,
        'bucket': bucket_step,
        'threadripper_token': write_step,
        'grafana_token': grafana_step,
        'grafana_source_bucket_ids': source_bucket_ids,
        'grafana_note': (
            f'Consolidated credential (option B, coordinator-approved 2026-09-15): creates one '
            f'NEW token, {grafana_description!r}, carrying read access to '
            f'{", ".join(ORIGINAL_GRAFANA_BUCKETS + (bucket_name,))}. The existing shared '
            f'{GRAFANA_SOURCE_DESCRIPTION!r} token is validated for exact scope but is never '
            'modified or revoked -- it stays active for rollback. Wiring the new token into '
            "Grafana's datasource (.env) and preserving its existing UID is that repo's own "
            'workflow, not performed here.'
        ),
    }


def fetch_state(org_name):
    orgs = json.loads(recovery.live('influx org list --json'))
    auths = json.loads(recovery.live(f'influx auth list --org {org_name} --json'))
    buckets = json.loads(recovery.live(f'influx bucket list --org {org_name} --json'))
    return orgs, buckets, auths


def preflight_secret_path(path):
    """Refuse to touch anything unexpected already sitting at the target
    path or its atomic-write temp file; only a brand-new file is safe."""
    if path.exists():
        raise RuntimeError(f'Refusing to overwrite unexpected existing file at {path}')
    tmp = path.with_name(path.name + '.tmp')
    if tmp.exists():
        raise RuntimeError(f'Refusing to overwrite unexpected existing temp file at {tmp}')
    return tmp


def write_secret_atomic(path, tmp, payload):
    """Exclusive-create, mode 0600, then atomic rename. On Windows the ACL
    comes from the parent secrets/ directory's inherited permissions (set up
    by recovery.private_directory), not a per-file icacls call."""
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    if os.name != 'nt':
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def ensure_token(step, org_name, org_id, permission_bucket_ids, kind, secret_path):
    if step['action'] == 'skip':
        return {'action': 'skip', 'id': step['id'], 'description': step['description']}

    validate_id('org id', org_id)
    for bucket_id in permission_bucket_ids:
        validate_id('bucket id', bucket_id)

    description = step['description']
    tmp_path = preflight_secret_path(secret_path)
    recovery.private_directory(secret_path.parent)

    flag = '--write-bucket' if kind == 'write' else '--read-bucket'
    bucket_args = ' '.join(f'{flag} {bucket_id}' for bucket_id in permission_bucket_ids)
    created = json.loads(recovery.live(
        f'influx auth create --org {org_name} {bucket_args} '
        f'--description "{description}" --json'))
    rows = created if isinstance(created, list) else [created]
    if len(rows) != 1:
        raise RuntimeError(f'Unexpected auth create result shape for {description!r}')
    row = rows[0]

    # Persist the only copy immediately: it cannot be re-read from Influx
    # later, so a failure in the validation below must not lose it.
    payload = (json.dumps({
        'url': INFLUX_URL, 'org': org_name, 'auth_id': row['id'],
        'description': description, 'token': row['token'],
    }) + '\n').encode()
    try:
        write_secret_atomic(secret_path, tmp_path, payload)
    except OSError as exc:
        raise RuntimeError(
            f'Created token {description!r} (id {row["id"]}) live but FAILED to persist its '
            f'only local copy to {secret_path} ({exc.__class__.__name__}). The token value is '
            'now unrecoverable from this script and this script never revokes tokens '
            'automatically -- manual reconciliation required.'
        ) from None

    if row['status'] != 'active':
        raise RuntimeError(
            f'New token {description!r} (id {row["id"]}) is not active; it has been saved to '
            f'{secret_path} for manual review, but this script never revokes tokens automatically')
    expected = expected_permissions(kind, org_id, permission_bucket_ids)
    if set(row['permissions']) != expected:
        raise RuntimeError(
            f'New token {description!r} (id {row["id"]}) has unexpected permissions '
            f'{sorted(row["permissions"])}, expected exactly {sorted(expected)}; it has been '
            f'saved to {secret_path} for manual review, but this script never revokes tokens '
            'automatically')
    return {'action': 'create', 'id': row['id'], 'description': description}


def apply_plan(plan, org_name, bucket_name, retention_days):
    org_id = validate_id('org id', plan['org_id'])
    bucket_step = plan['bucket']
    if bucket_step['action'] == 'create':
        created = json.loads(recovery.live(
            f'influx bucket create --org {org_name} --name {bucket_name} '
            f'--retention {retention_days}d --json'))
        bucket_id = validate_id('bucket id', created['id'])
    else:
        bucket_id = validate_id('bucket id', bucket_step['id'])

    grafana_bucket_ids = plan['grafana_source_bucket_ids'] + [bucket_id]

    return {
        'bucket_id': bucket_id,
        'org_id': org_id,
        'threadripper_token': ensure_token(
            plan['threadripper_token'], org_name, org_id, [bucket_id], 'write', WRITE_SECRET_PATH),
        'grafana_token': ensure_token(
            plan['grafana_token'], org_name, org_id, grafana_bucket_ids, 'read', GRAFANA_SECRET_PATH),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--org', default=DEFAULT_ORG)
    parser.add_argument('--bucket', default=DEFAULT_BUCKET)
    parser.add_argument('--retention-days', type=int, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument('--apply', action='store_true',
                         help='Actually create the bucket/tokens; default is dry-run/plan-only')
    args = parser.parse_args(argv)
    validate_name('--org', args.org)
    validate_name('--bucket', args.bucket)
    if args.retention_days <= 0:
        raise ValueError('--retention-days must be positive')

    orgs, buckets, auths = fetch_state(args.org)
    plan = build_plan(orgs, buckets, auths, args.org, args.bucket, args.retention_days)

    if not args.apply:
        print(json.dumps({'mode': 'dry-run', 'plan': plan}, indent=2))
        return

    result = apply_plan(plan, args.org, args.bucket, args.retention_days)
    print(json.dumps({'mode': 'apply', 'result': result}, indent=2))


if __name__ == '__main__':
    main()
