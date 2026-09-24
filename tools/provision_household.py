"""Idempotent provisioning for the household observability pilot (M3): the
InfluxDB `security` bucket (90 d) and five scoped tokens in org `home`.

  household-evaluator   read infra,network   write infra
  security-aggregator   read infra,network   write security
  telegraf-pi           write infra
  telegraf-ryzen        write infra
  grafana read-only (iot, network, voice_telemetry, infra, security)
                        read all five        (new consolidated Grafana reader)

Modelled on tools/provision_infra.py: same `recovery` import, same validation,
same atomic secret writer, dry-run (plan only) unless `--apply`, never prints
or logs a token value. New tokens are persisted only to ACL-protected files
under ignored `secrets/` as `secrets/household-<name>-token.json`, and the
evaluator/aggregator tokens are additionally written as `INFLUX_TOKEN=...`
env files under ../grafana/pilot/secrets/ (owner-only, gitignored) for the
compose override.

The two existing Grafana readers ('grafana read-only (iot, network,
voice_telemetry)' and '... , infra)') are validated but never modified or
revoked. Wiring the new 5-bucket reader into Grafana's .env is a SEPARATE
later step (grafana/tools/activate_infra_reader.py pattern); this script only
prints that instruction. See grafana/pilot/CONTRACT.md (D6, A§7).
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
SECURITY_BUCKET = 'security'
SECURITY_RETENTION_DAYS = 90
INFLUX_URL = 'http://10.77.77.1:8086'
# Probes run inside the existing InfluxDB container, not over a host LAN route.
PROBE_URL = 'http://127.0.0.1:8086'
NAME_PATTERN = re.compile(r'[A-Za-z0-9_-]+')
ID_PATTERN = re.compile(r'[0-9a-fA-F]{16}')

SECRETS_DIR = ROOT / 'secrets'
GRAFANA_PILOT_SECRETS_DIR = (ROOT.parent / 'grafana' / 'pilot' / 'secrets').resolve()

# Buckets that must already exist; ids are read live and validated.
EXISTING_BUCKETS = ('iot', 'network', 'voice_telemetry', 'infra')
# The reader Grafana uses today (activated 2026-09-15). Validated for exact
# scope so the new reader is provably a superset; never mutated.
GRAFANA_CURRENT_READER = 'grafana read-only (iot, network, voice_telemetry, infra)'
GRAFANA_CURRENT_READER_BUCKETS = ('iot', 'network', 'voice_telemetry', 'infra')
GRAFANA_ORIGINAL_READER = 'grafana read-only (iot, network, voice_telemetry)'
GRAFANA_NEW_READER = 'grafana read-only (iot, network, voice_telemetry, infra, security)'

# name -> (influx description, read buckets, write buckets, env file or None)
TOKENS = {
    'evaluator': ('household-evaluator', ('infra', 'network'), ('infra',), 'household-evaluator.env'),
    'aggregator': ('security-aggregator', ('infra', 'network'), (SECURITY_BUCKET,), 'security-aggregator.env'),
    'telegraf-pi': ('telegraf-pi', (), ('infra',), None),
    'telegraf-ryzen': ('telegraf-ryzen', (), ('infra',), None),
    'grafana-reader': (GRAFANA_NEW_READER, ('iot', 'network', 'voice_telemetry', 'infra', SECURITY_BUCKET), (), None),
}


def secret_path(name):
    return SECRETS_DIR / f'household-{name}-token.json'


def env_path(filename):
    return GRAFANA_PILOT_SECRETS_DIR / filename


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
        raise RuntimeError(f'Bucket {name!r} not found; required for household token scopes')
    return bucket


def expected_permissions(org_id, read_ids, write_ids):
    return ({f'read:orgs/{org_id}/buckets/{bid}' for bid in read_ids} |
            {f'write:orgs/{org_id}/buckets/{bid}' for bid in write_ids})


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


def validate_current_grafana_reader(auths, org_id, bucket_ids):
    """The 4-bucket reader Grafana uses today must exist once, be active and
    carry exactly read on iot/network/voice_telemetry/infra. Never mutated."""
    matches = [a for a in auths if a.get('description') == GRAFANA_CURRENT_READER]
    if len(matches) != 1:
        raise RuntimeError(
            f'Expected exactly one token described {GRAFANA_CURRENT_READER!r}, found {len(matches)}; '
            'refusing to plan a consolidated Grafana reader from an ambiguous source')
    source = matches[0]
    if source['status'] != 'active':
        raise RuntimeError(f'Current Grafana reader is not active ({source["status"]!r}); needs manual review')
    expected = expected_permissions(org_id, bucket_ids, [])
    if set(source['permissions']) != expected:
        raise RuntimeError(
            f'Current Grafana reader has unexpected scopes {sorted(source["permissions"])}, '
            f'expected exactly {sorted(expected)}; refusing')
    return {'id': validate_id('auth id', source['id']), 'description': GRAFANA_CURRENT_READER}


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
    config = f'url = "{url}"\nheader = "Authorization: Token {token}"\n'
    out = recovery.command(['docker', 'exec', '-i', 'iot-influxdb', 'curl',
                            '--silent', '--max-time', '10', '--output', '/dev/null',
                            '--write-out', '%{http_code}', '--config', '-'] + extra,
                           input=config.encode(), timeout=20)
    return out.decode().strip() in ok_codes


def load_local_credential(path, auth_id):
    if not path.exists():
        raise RuntimeError(
            f'Existing active token (id {auth_id}) has no local credential file at '
            f'{path}; cannot verify it is usable. Refusing to silently skip or rotate -- '
            'token secrets cannot be re-read from Influx, this needs manual reconciliation.')
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f'Local credential file at {path} is unreadable/corrupt '
            f'({exc.__class__.__name__}); refusing to treat the existing token as provisioned') from None
    if saved.get('auth_id') != auth_id:
        raise RuntimeError(
            f'Local credential file at {path} is for a different token id '
            f'({saved.get("auth_id")!r}) than the existing live token ({auth_id!r}); refusing to skip')
    token = saved.get('token')
    if not token:
        raise RuntimeError(f'Local credential file at {path} has no token value; refusing to skip')
    return token


def verify_local_credential(path, auth_id, kind, org_name, org_id, bucket_id):
    token = load_local_credential(path, auth_id)
    if not probe_saved_token(kind, org_name, org_id, bucket_id, token):
        raise RuntimeError(
            f'Saved credential for token id {auth_id} failed a harmless authenticated probe; '
            'it may have been revoked or corrupted. Refusing to silently skip or rotate.')


def plan_token(auths, name, org_name, org_id, bucket_ids):
    description, read_names, write_names, env_file = TOKENS[name]
    path = secret_path(name)
    needs_security = SECURITY_BUCKET in read_names + write_names
    step = {'name': name, 'description': description, 'read': list(read_names),
            'write': list(write_names), 'secret': str(path)}
    if env_file:
        step['env_file'] = {'path': str(env_path(env_file)), 'exists': env_path(env_file).exists()}
    matches = [a for a in auths if a.get('description') == description]
    if not matches:
        step['action'] = 'create'
        return step
    if len(matches) > 1:
        raise RuntimeError(f'Multiple existing tokens with description {description!r}; ambiguous, refusing')
    match = matches[0]
    if needs_security and bucket_ids.get(SECURITY_BUCKET) is None:
        raise RuntimeError(
            f'Token {description!r} already exists (id {match["id"]}) but bucket {SECURITY_BUCKET!r} '
            'does not exist yet; inconsistent state, refusing to plan blindly')
    if match['status'] != 'active':
        raise RuntimeError(f'Existing token {description!r} is not active ({match["status"]!r}); needs manual review')
    expected = expected_permissions(org_id, [bucket_ids[n] for n in read_names], [bucket_ids[n] for n in write_names])
    if set(match['permissions']) != expected:
        raise RuntimeError(
            f'Existing token {description!r} has unexpected permissions {sorted(match["permissions"])}, '
            f'expected exactly {sorted(expected)}; refusing to treat as already provisioned')
    kind, probe_bucket = ('read', read_names[0]) if read_names else ('write', write_names[0])
    verify_local_credential(path, match['id'], kind, org_name, org_id, bucket_ids[probe_bucket])
    step.update(action='skip', id=match['id'], reason='already provisioned; local credential verified usable')
    return step


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
    comes from the parent directory's inherited permissions (set up by
    recovery.private_directory), not a per-file icacls call."""
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


def build_plan(orgs, buckets, auths, org_name):
    org = find_org(orgs, org_name)
    org_id = validate_id('org id', org['id'])
    bucket_ids = {name: validate_id('bucket id', require_bucket(buckets, name)['id'])
                  for name in EXISTING_BUCKETS}
    current_reader = validate_current_grafana_reader(
        auths, org_id, [bucket_ids[n] for n in GRAFANA_CURRENT_READER_BUCKETS])
    original_reader_present = any(a.get('description') == GRAFANA_ORIGINAL_READER for a in auths)

    bucket_step = plan_bucket(buckets, SECURITY_BUCKET, SECURITY_RETENTION_DAYS)
    bucket_ids[SECURITY_BUCKET] = bucket_step.get('id')

    token_steps = {name: plan_token(auths, name, org_name, org_id, bucket_ids) for name in TOKENS}
    for name, step in token_steps.items():
        if step['action'] == 'create':
            preflight_secret_path(secret_path(name))
            if step.get('env_file'):
                preflight_secret_path(Path(step['env_file']['path']))

    return {
        'org': org['name'],
        'org_id': org_id,
        'existing_bucket_ids': {n: bucket_ids[n] for n in EXISTING_BUCKETS},
        'bucket': bucket_step,
        'tokens': token_steps,
        'grafana_readers_retained': {
            'current': current_reader,
            'original_present': original_reader_present,
            'note': 'validated only; neither existing reader is modified or revoked (rollback path)',
        },
        'separate_later_step': (
            'Grafana reader rotation is NOT performed here. After --apply, a separate attended '
            f'step swaps INFLUXDB_READ_TOKEN in grafana/.env to the new {GRAFANA_NEW_READER!r} '
            f'token saved at {secret_path("grafana-reader")} (grafana/tools/activate_infra_reader.py '
            'pattern: rollback copy in the recovery-keys area, then `docker compose up -d`; that tool '
            'currently hard-codes the 4-bucket reader and needs a generalized credential/description '
            'argument first). Both previous readers stay active until separately authorized.'
        ),
    }


def fetch_state(org_name):
    orgs = json.loads(recovery.live('influx org list --json'))
    auths = json.loads(recovery.live(f'influx auth list --org {org_name} --json'))
    buckets = json.loads(recovery.live(f'influx bucket list --org {org_name} --json'))
    return orgs, buckets, auths


def ensure_token(step, org_name, org_id, bucket_ids):
    if step['action'] == 'skip':
        return {'action': 'skip', 'id': step['id'], 'description': step['description']}
    validate_id('org id', org_id)
    name, description = step['name'], step['description']
    read_ids = [validate_id('bucket id', bucket_ids[n]) for n in step['read']]
    write_ids = [validate_id('bucket id', bucket_ids[n]) for n in step['write']]
    path = secret_path(name)
    tmp_path = preflight_secret_path(path)
    recovery.private_directory(path.parent)

    bucket_args = ' '.join([f'--read-bucket {b}' for b in read_ids] + [f'--write-bucket {b}' for b in write_ids])
    created = json.loads(recovery.live(
        f'influx auth create --org {org_name} {bucket_args} --description "{description}" --json'))
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
        write_secret_atomic(path, tmp_path, payload)
    except OSError as exc:
        raise RuntimeError(
            f'Created token {description!r} (id {row["id"]}) live but FAILED to persist its '
            f'only local copy to {path} ({exc.__class__.__name__}). The token value is '
            'now unrecoverable from this script and this script never revokes tokens '
            'automatically -- manual reconciliation required.') from None

    if row['status'] != 'active':
        raise RuntimeError(
            f'New token {description!r} (id {row["id"]}) is not active; it has been saved to '
            f'{path} for manual review, but this script never revokes tokens automatically')
    expected = expected_permissions(org_id, read_ids, write_ids)
    if set(row['permissions']) != expected:
        raise RuntimeError(
            f'New token {description!r} (id {row["id"]}) has unexpected permissions '
            f'{sorted(row["permissions"])}, expected exactly {sorted(expected)}; it has been '
            f'saved to {path} for manual review, but this script never revokes tokens automatically')
    return {'action': 'create', 'id': row['id'], 'description': description}


def ensure_env_file(step, result):
    """INFLUX_TOKEN=... for the compose override, derived from the saved credential."""
    env = step.get('env_file')
    if not env:
        return None
    target = Path(env['path'])
    if target.exists():
        return {'path': str(target), 'action': 'skip', 'reason': 'already present (not re-read)'}
    tmp = preflight_secret_path(target)
    token = load_local_credential(secret_path(step['name']), result['id'])
    recovery.private_directory(target.parent)
    write_secret_atomic(target, tmp, f'INFLUX_TOKEN={token}\n'.encode())
    return {'path': str(target), 'action': 'create'}


def apply_plan(plan, org_name):
    org_id = validate_id('org id', plan['org_id'])
    bucket_ids = dict(plan['existing_bucket_ids'])
    bucket_step = plan['bucket']
    if bucket_step['action'] == 'create':
        created = json.loads(recovery.live(
            f'influx bucket create --org {org_name} --name {SECURITY_BUCKET} '
            f'--retention {SECURITY_RETENTION_DAYS}d --json'))
        bucket_ids[SECURITY_BUCKET] = validate_id('bucket id', created['id'])
    else:
        bucket_ids[SECURITY_BUCKET] = validate_id('bucket id', bucket_step['id'])

    results = {}
    for name, step in plan['tokens'].items():
        results[name] = ensure_token(step, org_name, org_id, bucket_ids)
        env = ensure_env_file(step, results[name])
        if env:
            results[name]['env_file'] = env
    return {'bucket_id': bucket_ids[SECURITY_BUCKET], 'org_id': org_id, 'tokens': results,
            'separate_later_step': plan['separate_later_step']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--org', default=DEFAULT_ORG)
    parser.add_argument('--apply', action='store_true',
                        help='Actually create the bucket/tokens/env files; default is dry-run/plan-only')
    args = parser.parse_args(argv)
    validate_name('--org', args.org)

    orgs, buckets, auths = fetch_state(args.org)
    plan = build_plan(orgs, buckets, auths, args.org)

    if not args.apply:
        print(json.dumps({'mode': 'dry-run', 'plan': plan}, indent=2))
        return

    result = apply_plan(plan, args.org)
    print(json.dumps({'mode': 'apply', 'result': result}, indent=2))


if __name__ == '__main__':
    main()
