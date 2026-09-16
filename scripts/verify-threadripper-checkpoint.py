"""Off-host-key restore drill for a Threadripper-held iot-backend checkpoint.

Proves that /home/david/iot-checkpoints/<stamp>.tar can be restored with the
key held on Threadripper (/etc/influxdb-standby/backup-password, root-only),
without the PC key and without touching production. Runs on the PC and issues
every remote step over the fixed read-only SSH prefix; nothing is copied to
Threadripper and nothing is decrypted on the PC. There is no PC-side key,
password or --key/--password-file flag anywhere in this script: KEY below is
only ever substituted into the sudo command text that runs on Threadripper,
so PC-key substitution is structurally impossible, not just discouraged.

Phases (one invocation runs them in order; --resume skips to verify):

  prepare  archive facts (size, sha256, restic version, free space), a fresh
           private temp dir under /home/david/ (mktemp, 0700), tar extraction,
           and the key-readability check. The key is root-only, so restic is
           NOT run by this script: it prints the exact single sudo command the
           user runs in an interactive SSH session, then waits for Enter. That
           command now also writes `restic snapshots --json` to
           <tmp>/snapshots.json, so --resume below can check identity.
  resume   (--resume TMPDIR, skips prepare) independently re-derives archive
           and snapshot identity instead of trusting the temp dir's name or a
           stale prepare() report: recomputes the archive sha256 (checked
           against --expected-sha256 if given) and compares the snapshot id in
           <tmp>/encryption-verification.json against the id restic actually
           restored, read from <tmp>/snapshots.json (the key needed to ask
           restic directly is root-only and unavailable to this script). Fails
           before any credential probing on a sha mismatch, a missing
           restore/, or a missing/mismatched snapshots.json.
  verify   a helper sent to python3 on Threadripper parses the two restored
           *-infra-token.json files, checks auth_id/description, and (unless
           --no-probe) sends each token through a harmless curl probe with the
           credential on curl's stdin (never argv). Only auth_id, description
           and the HTTP code come back. On overall success this also writes a
           local, token-free audit record to data/<tmp-basename>-record.json
           (stamp, archive path, sha256, snapshot id, the Threadripper key
           *path* only, restic version, and per-credential label/auth_id/
           description/probe_ok, with start/completion timestamps) using the
           same private-directory helper as the rest of this repo's recovery
           tooling.
  cleanup  shred -u every file in the temp dir and rm -rf it, also on failure.
           This is ordinary best-effort cleanup (shred -u, then rm -rf) -- it
           is NOT guaranteed secure erasure on SSD/flash media, which can
           retain data past a logical delete; treat the drill as having
           exposed the restored credentials to that temp dir accordingly.

Token values are loaded only inside the remote helper, whose single output
function raises if any loaded token appears in the text; the PC side rejects
any output containing a token-shaped run or a "token" key as defence in depth,
including in the record file written above.

--dry-run prints the planned remote commands (paths only) and exits.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('recovery', ROOT / 'scripts/influx-recovery.py')
recovery = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(recovery)  # scripts/influx-recovery.py: private_directory()

SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=yes',
       '-o', 'HostKeyAlias=192.168.1.105', 'david@192.168.1.106']
HOME = '/home/david'
ARCHIVES = HOME + '/iot-checkpoints'
KEY = '/etc/influxdb-standby/backup-password'
INCLUDE = '/checkpoint/credentials/*-infra-token.json'
PROBE_URL = 'http://10.77.77.1:8086'
DEFAULT_ORG, DEFAULT_ORG_ID, DEFAULT_BUCKET_ID = 'home', '714f34e4c62e3500', '883c17ff19b886d4'
EXPECTED = {'threadripper-infra-token.json': ('1155d1b0f9d87000', 'threadripper infra write-only, infra bucket', 'write'),
            'grafana-infra-token.json': ('1155d1b13d987000', 'grafana read-only (iot, network, voice_telemetry, infra)', 'read')}
STAMP = re.compile(r'\d{8}T\d{6}Z')
TMP = re.compile(HOME + r'/iot-drill-[A-Za-z0-9]{8}')
ID = re.compile(r'[0-9a-f]{16}')
NAME = re.compile(r'[A-Za-z0-9_-]+')
TOKEN_SHAPE = re.compile(r'[A-Za-z0-9+/_=-]{80,}')  # InfluxDB tokens are 88 chars; ids/hashes are 16/64

# Runs on Threadripper as `python3 - <tmp> <probe|noprobe> <org> <org_id> <bucket_id>`.
REMOTE_VERIFY = r'''
import json, re, subprocess, sys
tmp, probe, org, org_id, bucket_id = sys.argv[1:6]
EXPECTED = %(expected)s
loaded = set()
def emit(obj):
    text = json.dumps(obj)
    for t in loaded:
        if t and t in text: raise RuntimeError('Refusing to print output that contains a restored token')
    print(text)
def curl(kind, token):
    if kind == 'write':
        url = '%(url)s/api/v2/write?org=' + org + '&bucket=' + bucket_id
        extra, ok = ['--request', 'POST', '--data-binary', ''], {'400', '204'}  # empty body: 400 or 204 both prove auth; 401/403 do not
    else:
        url = '%(url)s/api/v2/buckets?orgID=' + org_id + '&limit=1'
        extra, ok = [], {'200'}
    config = 'url = "' + url + '"\nheader = "Authorization: Token ' + token + '"\n'
    p = subprocess.run(['curl', '--silent', '--max-time', '10', '--output', '/dev/null',
                        '--write-out', '%%{http_code}', '--config', '-'] + extra,
                       input=config.encode(), capture_output=True, timeout=20)
    code = p.stdout.decode().strip() or 'none'
    return code, code in ok
results = []
for label, (auth_id, description, kind) in EXPECTED.items():
    path = tmp + '/restore/checkpoint/credentials/' + label
    row = dict(label=label, kind=kind, expected_auth_id=auth_id)
    try:
        with open(path, 'rb') as f: saved = json.loads(f.read().decode())
    except OSError as exc:
        row.update(present=False, error=exc.__class__.__name__); results.append(row); continue
    except ValueError:
        row.update(present=True, parsed=False); results.append(row); continue
    token = saved.get('token')
    if isinstance(token, str) and token: loaded.add(token)
    shape_ok = isinstance(token, str) and re.fullmatch(r'[A-Za-z0-9_+=/-]+', token) is not None
    row.update(present=True, parsed=True, auth_id=saved.get('auth_id'), description=saved.get('description'),
               auth_id_match=saved.get('auth_id') == auth_id, description_match=saved.get('description') == description,
               token_present=bool(token), token_shape_ok=shape_ok)
    if probe == 'probe' and shape_ok:
        code, ok = curl(kind, token)
        row.update(probe_http=code, probe_ok=ok)
    results.append(row)
emit(dict(credentials=results))
'''


def emit(text):
    """Only output path on the PC. Rejects token-shaped material from remote output."""
    if TOKEN_SHAPE.search(text) or '"token"' in text:
        raise RuntimeError('Refusing to print output that looks like it contains a token')
    print(text)


class Remote:
    def __init__(self, dry_run):
        self.dry_run, self.planned = dry_run, []

    def run(self, command, stdin=None, check=True, timeout=120):
        self.planned.append(command)
        if self.dry_run:
            emit('  ssh ... "%s"' % command)
            return ''
        p = subprocess.run(SSH + [command], input=stdin, capture_output=True, timeout=timeout)
        out = p.stdout.decode(errors='replace')
        if check and p.returncode:
            raise RuntimeError('Remote step failed (exit %d): %s' % (p.returncode, command.split(' ')[0]))
        return out


def sudo_command(tmp):
    return ("sudo -- sh -c 'umask 077; export RESTIC_REPOSITORY=%s/repository RESTIC_PASSWORD_FILE=%s; "
            "restic --no-cache check && restic --no-cache restore latest --target %s/restore --verify "
            "--include \"%s\" && restic --no-cache snapshots --json > %s/snapshots.json && "
            "chown -R david:david %s'" % (tmp, KEY, tmp, INCLUDE, tmp, tmp))


def cleanup(remote, tmp):
    remote.run('find %s -type f -exec shred -u -- {} + 2>/dev/null; rm -rf -- %s; test ! -e %s' % (tmp, tmp, tmp),
               check=False)
    ok = True
    if not remote.dry_run and remote.run('test -e %s && echo present || echo gone' % tmp, check=False).strip() == 'present':
        emit('Temp dir still present (root-owned leftovers?). Run on Threadripper: sudo rm -rf -- %s' % tmp)
        ok = False
    if not remote.dry_run:
        emit('Cleanup used ordinary shred -u + rm -rf (best effort); this is NOT guaranteed '
             'secure erasure on SSD/flash media.')
    return ok


def prepare(remote, stamp, expected_sha):
    archive = '%s/%s.tar' % (ARCHIVES, stamp)
    facts = remote.run('test -f %s && stat -c %%s %s && sha256sum %s | cut -d" " -f1 && restic version && '
                       'df -B1 --output=avail %s | tail -1' % (archive, archive, archive, HOME))
    report = dict(archive=archive)
    if not remote.dry_run:
        size, sha, restic, avail = facts.split('\n')[:4]
        report.update(size=int(size), sha256=sha, restic=restic, home_avail_bytes=int(avail))
        if expected_sha and sha != expected_sha: raise RuntimeError('Archive sha256 differs from the expected value')
        if int(avail) < 3 * int(size) + 1024**3: raise RuntimeError('Not enough free space under ' + HOME)
    tmp = remote.run('umask 077; mktemp -d %s/iot-drill-XXXXXXXX' % HOME).strip() or HOME + '/iot-drill-XXXXXXXX'
    if not TMP.fullmatch(tmp): raise RuntimeError('Unexpected temp dir name')
    report['tmp'] = tmp
    try:
        remote.run('tar -xf %s -C %s && test -d %s/repository' % (archive, tmp, tmp))
        listing = remote.run('ls %s/repository/snapshots; cat %s/encryption-verification.json' % (tmp, tmp))
        if not remote.dry_run:
            lines = listing.strip().split('\n', 1)
            report['snapshot'] = lines[0]
            report['encryption_verification'] = json.loads(lines[1])
            if report['encryption_verification'].get('snapshot') != lines[0]:
                raise RuntimeError('Snapshot id in encryption-verification.json differs from repository/snapshots')
        readable = remote.run('test -r %s && echo yes || echo no' % KEY, check=False).strip()
        report['key_readable_by_david'] = readable == 'yes'
        if readable == 'yes':
            # Not expected (root-only). If it ever is, no sudo is needed.
            remote.run('export RESTIC_REPOSITORY=%s/repository RESTIC_PASSWORD_FILE=%s; restic --no-cache check && '
                       'restic --no-cache restore latest --target %s/restore --verify --include "%s"' % (tmp, KEY, tmp, INCLUDE),
                       timeout=600)
            report['restic_run_by'] = 'david'
        else:
            report['restic_run_by'] = 'sudo (user)'
    except Exception:
        cleanup(remote, tmp)
        raise
    return report


def verify_archive_identity(remote, tmp, stamp, expected_sha):
    """On --resume, independently re-derive archive/snapshot identity rather
    than trusting the temp dir's name or a stale prepare() report. Recomputes
    the archive sha256 (compared to --expected-sha256 if given) and fails
    before touching the temp dir at all on a mismatch. Then requires
    restore/checkpoint/credentials to exist, and compares the snapshot id in
    <tmp>/encryption-verification.json against the id restic actually
    restored, read from <tmp>/snapshots.json -- the key needed to ask restic
    directly is root-only, so this script cannot query it itself."""
    archive = '%s/%s.tar' % (ARCHIVES, stamp)
    sha = remote.run('sha256sum %s | cut -d" " -f1' % archive).strip()
    if remote.dry_run:
        remote.run('restic version')
        remote.run('test -d %s/restore/checkpoint/credentials && echo yes || echo no' % tmp, check=False)
        remote.run('cat %s/encryption-verification.json' % tmp)
        remote.run('cat %s/snapshots.json 2>/dev/null || true' % tmp, check=False)
        return dict(archive=archive)
    if expected_sha and sha != expected_sha:
        raise RuntimeError('Archive sha256 differs from the expected value on resume')
    restic_version = remote.run('restic version').strip()
    restored = remote.run('test -d %s/restore/checkpoint/credentials && echo yes || echo no'
                          % tmp, check=False).strip()
    if restored != 'yes':
        raise RuntimeError('No restore/checkpoint/credentials directory in %s; run the sudo '
                           'restore command below before --resume' % tmp)
    verification = json.loads(remote.run('cat %s/encryption-verification.json' % tmp))
    snapshots_out = remote.run('cat %s/snapshots.json 2>/dev/null || true' % tmp, check=False).strip()
    if not snapshots_out:
        raise RuntimeError('%s/snapshots.json is missing; re-run the sudo command below (it now '
                           'writes `restic snapshots --json` there) before --resume' % tmp)
    snapshots = json.loads(snapshots_out)
    if not isinstance(snapshots, list) or len(snapshots) != 1:
        raise RuntimeError('Expected exactly one restic snapshot recorded in %s/snapshots.json, found %r'
                           % (tmp, len(snapshots) if isinstance(snapshots, list) else snapshots))
    restored_id = snapshots[0].get('id')
    expected_id = verification.get('snapshot')
    if not restored_id or restored_id != expected_id:
        raise RuntimeError('Restored restic snapshot id %r does not match encryption-verification.json '
                           'snapshot %r' % (restored_id, expected_id))
    return dict(archive=archive, sha256=sha, restic=restic_version, snapshot=expected_id)


def write_record(report):
    """Best-effort local audit record of a *successful* drill, written under
    this repo's private data/ directory (see recovery.private_directory).
    Contains only already-sanitised fields (auth_id/description/probe_ok,
    the Threadripper key *path*, never a token) with the same guard used for
    printed output, as defence in depth."""
    recovery.private_directory(ROOT / 'data')
    name = report['tmp'].rsplit('/', 1)[-1] + '-record.json'
    payload = dict(
        generated_at=datetime.now(timezone.utc).isoformat(),
        started_at=report.get('started_at'),
        stamp=report['stamp'],
        archive=report['archive'],
        sha256=report['sha256'],
        snapshot=report['snapshot'],
        key_path=KEY,
        restic_version=report.get('restic'),
        credentials=[dict(label=c.get('label'), auth_id=c.get('auth_id'), description=c.get('description'),
                          probe_ok=c.get('probe_ok')) for c in report['credentials']],
    )
    text = json.dumps(payload, indent=2) + '\n'
    if TOKEN_SHAPE.search(text) or '"token"' in text:
        raise RuntimeError('Refusing to write a record that looks like it contains a token')
    path = ROOT / 'data' / name
    path.write_text(text, encoding='utf-8', newline='\n')
    return path


def verify(remote, tmp, probe, org, org_id, bucket_id):
    remote.run('test -d %s/restore/checkpoint/credentials' % tmp)
    helper = REMOTE_VERIFY % dict(expected=repr(EXPECTED), url=PROBE_URL)
    out = remote.run('python3 - %s %s %s %s %s' % (tmp, 'probe' if probe else 'noprobe', org, org_id, bucket_id),
                     stdin=helper.encode(), timeout=120)
    if remote.dry_run: return dict(credentials=[])
    result = json.loads(out.strip().split('\n')[-1])
    for row in result['credentials']:
        row['ok'] = bool(row.get('present') and row.get('parsed') and row.get('auth_id_match')
                         and row.get('description_match') and row.get('token_shape_ok')
                         and (not probe or row.get('probe_ok') is True))
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--stamp', default='20260915T234120Z', help='archive stamp under ' + ARCHIVES)
    p.add_argument('--expected-sha256', default=None, help='fail if the remote archive sha256 differs')
    p.add_argument('--resume', metavar='TMPDIR', help='skip prepare; verify an already restored temp dir')
    p.add_argument('--no-wait', action='store_true', help='print the sudo command and exit 2 instead of waiting')
    p.add_argument('--no-probe', action='store_true', help='skip the InfluxDB probes')
    p.add_argument('--org', default=DEFAULT_ORG)
    p.add_argument('--org-id', default=DEFAULT_ORG_ID)
    p.add_argument('--bucket-id', default=DEFAULT_BUCKET_ID)
    p.add_argument('--dry-run', action='store_true', help='print planned remote commands only')
    a = p.parse_args(argv)
    for value, pattern, what in ((a.stamp, STAMP, '--stamp'), (a.org, NAME, '--org'), (a.org_id, ID, '--org-id'),
                                 (a.bucket_id, ID, '--bucket-id')):
        if not pattern.fullmatch(value): p.error('%s has an unexpected form' % what)
    if a.resume and not TMP.fullmatch(a.resume): p.error('--resume must be a %s/iot-drill-XXXXXXXX path' % HOME)
    if a.expected_sha256 and not re.fullmatch(r'[0-9a-f]{64}', a.expected_sha256): p.error('--expected-sha256 form')
    remote = Remote(a.dry_run)
    report = dict(ok=False, stamp=a.stamp, dry_run=a.dry_run,
                  started_at=datetime.now(timezone.utc).isoformat())
    tmp = a.resume
    try:
        if not a.resume:
            report.update(prepare(remote, a.stamp, a.expected_sha256))
            tmp = report['tmp']
            if report.get('restic_run_by') != 'david':
                emit('\nThe Threadripper key is root-only. Run this ONE command in an interactive SSH session '
                     '(ssh david@192.168.1.106), then press Enter here:\n\n  %s\n' % sudo_command(tmp))
                if a.no_wait:
                    emit('Then resume with: python scripts/verify-threadripper-checkpoint.py --resume %s' % tmp)
                    emit('(the temp dir is left in place for the resume; it is removed at the end of that run)')
                    tmp = None  # keep it for the resume
                    return 2
                if not a.dry_run: sys.stdin.readline()
        else:
            report.update(verify_archive_identity(remote, tmp, a.stamp, a.expected_sha256))
            report['tmp'] = tmp
        report.update(verify(remote, tmp, not a.no_probe, a.org, a.org_id, a.bucket_id))
        report['ok'] = bool(report['credentials']) and all(r['ok'] for r in report['credentials'])
        if report['ok'] and not a.dry_run:
            report['record'] = str(write_record(report))
            emit('Record written: %s' % report['record'])
    except Exception as exc:
        report.update(error=exc.__class__.__name__, detail=str(exc))
    finally:
        if tmp: report['cleaned'] = cleanup(remote, tmp)
    emit(json.dumps(report, indent=2))
    return 0 if report['ok'] or a.dry_run else 1


if __name__ == '__main__': sys.exit(main())
