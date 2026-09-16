"""Unit tests for scripts/verify-threadripper-checkpoint.py with the SSH
transport (subprocess.run, the function Remote.run calls) fully mocked.

No real network, no real Threadripper, no real restic and no real tokens are
ever involved -- FakeSSH answers each remote command by pattern-matching the
command text, the way FakeDocker does in test_verify_credential_restore.py.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location(
    'verify_threadripper_checkpoint',
    Path(__file__).resolve().parents[1] / 'scripts/verify-threadripper-checkpoint.py')
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)

TMP_DIR = d.HOME + '/iot-drill-ABCDEFGH'
GOOD_SHA = 'f' * 64
SNAP = 'a' * 64
GOOD_CREDENTIALS = [
    {'label': 'threadripper-infra-token.json', 'kind': 'write', 'expected_auth_id': '1155d1b0f9d87000',
     'present': True, 'parsed': True, 'auth_id': '1155d1b0f9d87000',
     'description': 'threadripper infra write-only, infra bucket',
     'auth_id_match': True, 'description_match': True, 'token_present': True, 'token_shape_ok': True},
    {'label': 'grafana-infra-token.json', 'kind': 'read', 'expected_auth_id': '1155d1b13d987000',
     'present': True, 'parsed': True, 'auth_id': '1155d1b13d987000',
     'description': 'grafana read-only (iot, network, voice_telemetry, infra)',
     'auth_id_match': True, 'description_match': True, 'token_present': True, 'token_shape_ok': True},
]


def ok(text):
    return SimpleNamespace(stdout=(text if isinstance(text, bytes) else text.encode()), returncode=0)


class FakeSSH:
    """Records every call; answers each remote command by substring match.
    Also serves as the fake for recovery.command's subprocess.run calls
    (whoami / icacls), which fall through to the default success reply."""

    def __init__(self, *, archive_sha=GOOD_SHA, restic_version='restic 0.16.4',
                 snapshot_id=SNAP, restore_present=True, snapshots_json=None,
                 verify_result=None, fail_at=None, size=1000, avail=10 ** 12,
                 key_readable=False):
        self.calls = []
        self.archive_sha = archive_sha
        self.restic_version = restic_version
        self.snapshot_id = snapshot_id
        self.restore_present = restore_present
        self.snapshots_json = (snapshots_json if snapshots_json is not None
                                else json.dumps([{'id': snapshot_id}]))
        self.verify_result = verify_result if verify_result is not None else {'credentials': GOOD_CREDENTIALS}
        self.fail_at = fail_at
        self.size, self.avail, self.key_readable = size, avail, key_readable

    def __call__(self, args, input=None, capture_output=True, timeout=120):
        self.calls.append((list(args), input))
        cmd = args[-1] if args else ''
        if self.fail_at and self.fail_at in cmd:
            return SimpleNamespace(stdout=b'', returncode=1)
        if cmd.startswith('test -f') and 'stat -c' in cmd:
            return ok('\n'.join([str(self.size), self.archive_sha, self.restic_version, str(self.avail)]))
        if cmd.startswith('umask 077; mktemp'):
            return ok(TMP_DIR)
        if cmd.startswith('tar -xf'):
            return ok('')
        if cmd.startswith('ls ') and 'encryption-verification.json' in cmd:
            return ok(self.snapshot_id + '\n' + json.dumps({'snapshot': self.snapshot_id}))
        if cmd.startswith('test -r'):
            return ok('yes' if self.key_readable else 'no')
        if cmd.startswith('sha256sum'):
            return ok(self.archive_sha)
        if cmd == 'restic version':
            return ok(self.restic_version)
        if 'restore/checkpoint/credentials && echo yes' in cmd:
            return ok('yes' if self.restore_present else 'no')
        if cmd.startswith('cat ') and cmd.rstrip().endswith('encryption-verification.json'):
            return ok(json.dumps({'snapshot': self.snapshot_id}))
        if cmd.startswith('cat ') and 'snapshots.json' in cmd:
            return ok(self.snapshots_json)
        if cmd.startswith('test -d') and 'restore/checkpoint/credentials' in cmd:
            return ok('')
        if cmd.startswith('python3 -'):
            return ok(json.dumps(self.verify_result))
        return ok('')


def parse_report(out):
    """The final emit(json.dumps(report, indent=2)) is multi-line; find its
    unindented opening brace (nested dicts inside lists are indented) and
    parse from there to the end of the captured output."""
    lines = out.splitlines()
    start = max(i for i, line in enumerate(lines) if line == '{')
    return json.loads('\n'.join(lines[start:]))


@contextlib.contextmanager
def run(fake, argv, data_root=None):
    out = io.StringIO()
    patches = [mock.patch.object(d.subprocess, 'run', fake)]
    if data_root is not None:
        patches.append(mock.patch.object(d, 'ROOT', data_root))
    with contextlib.ExitStack() as stack:
        for p in patches: stack.enter_context(p)
        with contextlib.redirect_stdout(out):
            code = d.main(argv)
    yield code, out.getvalue()


class PrepareNoWaitTests(unittest.TestCase):
    def test_prepare_prints_sudo_command_and_exits_2(self):
        fake = FakeSSH()
        with run(fake, ['--no-wait']) as (code, out):
            pass
        self.assertEqual(code, 2)
        self.assertIn(d.sudo_command(TMP_DIR), out)
        self.assertIn('restic --no-cache snapshots --json > %s/snapshots.json' % TMP_DIR, out)
        self.assertIn('--resume %s' % TMP_DIR, out)
        # tmp is deliberately left in place (not cleaned) for the resume.
        self.assertFalse(any('shred' in (c[0][-1] if c[0] else '') for c in fake.calls))


class ResumeTests(unittest.TestCase):
    def test_resume_matching_snapshot_and_sha_passes_and_writes_record(self):
        fake = FakeSSH()
        with tempfile.TemporaryDirectory() as td:
            data_root = Path(td)
            with run(fake, ['--resume', TMP_DIR, '--expected-sha256', GOOD_SHA, '--no-probe'],
                     data_root=data_root) as (code, out):
                pass
            self.assertEqual(code, 0)
            report = parse_report(out)
            self.assertTrue(report['ok'])
            self.assertEqual(report['snapshot'], SNAP)
            self.assertEqual(report['sha256'], GOOD_SHA)
            record_path = data_root / 'data' / 'iot-drill-ABCDEFGH-record.json'
            self.assertTrue(record_path.is_file())
            record = json.loads(record_path.read_text())
            self.assertEqual(record['snapshot'], SNAP)
            self.assertEqual(record['sha256'], GOOD_SHA)
            self.assertEqual(record['key_path'], d.KEY)
            self.assertEqual([c['label'] for c in record['credentials']],
                             ['threadripper-infra-token.json', 'grafana-infra-token.json'])
            for c in record['credentials']:
                self.assertEqual(set(c), {'label', 'auth_id', 'description', 'probe_ok'})
            self.assertNotIn('"token":', json.dumps(record))  # labels legitimately end in "-token.json"

    def test_resume_sha_mismatch_fails_before_probing(self):
        fake = FakeSSH(archive_sha=GOOD_SHA)
        with run(fake, ['--resume', TMP_DIR, '--expected-sha256', 'b' * 64]) as (code, out):
            pass
        self.assertEqual(code, 1)
        report = parse_report(out)
        self.assertFalse(report['ok'])
        self.assertEqual(report['error'], 'RuntimeError')
        self.assertIn('sha256', report['detail'])
        self.assertFalse(any(c[0][-1].startswith('python3 -') for c in fake.calls))

    def test_resume_missing_restore_dir_fails_clearly(self):
        fake = FakeSSH(restore_present=False)
        with run(fake, ['--resume', TMP_DIR]) as (code, out):
            pass
        self.assertEqual(code, 1)
        report = parse_report(out)
        self.assertEqual(report['error'], 'RuntimeError')
        self.assertIn('restore', report['detail'])
        self.assertIn('--resume', report['detail'])
        self.assertFalse(any(c[0][-1].startswith('python3 -') for c in fake.calls))

    def test_resume_missing_snapshots_json_fails_clearly(self):
        fake = FakeSSH(snapshots_json='')
        with run(fake, ['--resume', TMP_DIR]) as (code, out):
            pass
        self.assertEqual(code, 1)
        report = parse_report(out)
        self.assertEqual(report['error'], 'RuntimeError')
        self.assertIn('snapshots.json', report['detail'])

    def test_resume_snapshot_id_mismatch_fails(self):
        fake = FakeSSH(snapshots_json=json.dumps([{'id': 'c' * 64}]))
        with run(fake, ['--resume', TMP_DIR]) as (code, out):
            pass
        self.assertEqual(code, 1)
        report = parse_report(out)
        self.assertEqual(report['error'], 'RuntimeError')
        self.assertIn('does not match', report['detail'])

    def test_cleanup_runs_on_failure(self):
        fake = FakeSSH(restore_present=False)
        with run(fake, ['--resume', TMP_DIR]) as (code, out):
            pass
        self.assertEqual(code, 1)
        self.assertTrue(any('shred' in c[0][-1] for c in fake.calls))
        self.assertTrue(any(c[0][-1].startswith('find %s' % TMP_DIR) for c in fake.calls))

    def test_dry_run_touches_nothing_and_prints_plan(self):
        def explode(*a, **k):
            raise AssertionError('subprocess.run must not be called in --dry-run')
        with run(explode, ['--resume', TMP_DIR, '--dry-run']) as (code, out):
            pass
        self.assertEqual(code, 0)
        self.assertIn('ssh ...', out)
        report = parse_report(out)
        self.assertTrue(report['dry_run'])
        self.assertNotIn('record', report)


class GuardTests(unittest.TestCase):
    def test_emit_guard_refuses_token_shaped_output(self):
        token_shaped = 'A' * 88
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                d.emit('leak: ' + token_shaped)
            with self.assertRaises(RuntimeError):
                d.emit('{"token": "short"}')
            d.emit('safe output')  # does not raise

    def test_write_record_guard_refuses_token_shaped_field(self):
        report = dict(tmp=TMP_DIR, stamp='20260915T234120Z', archive='x', sha256=GOOD_SHA,
                      snapshot=SNAP, restic='restic 0.16.4',
                      credentials=[{'label': 'x', 'auth_id': 'A' * 88, 'description': 'd', 'probe_ok': True}])
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(d, 'ROOT', Path(td)):
                with self.assertRaises(RuntimeError):
                    d.write_record(report)


if __name__ == '__main__':
    unittest.main()

class WriterProbeCodesTest(unittest.TestCase):
    def test_write_probe_accepts_204_and_400_only(self):
        # An empty-body write with a valid write token returns 204 (accepted) or 400
        # (bad body) depending on the server; 401/403 mean the token is invalid.
        # Observed 2026-09-16: InfluxDB 2.7.12 returned 204 during the real drill.
        src = d.REMOTE_VERIFY
        self.assertIn("{'400', '204'}", src)
        self.assertNotIn("{'400'}", src)
