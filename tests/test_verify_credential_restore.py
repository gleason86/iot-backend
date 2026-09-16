"""Unit tests for scripts/verify-credential-restore.py with every subprocess mocked.

The fake Docker creates fixture credential files in the drill's temporary
directory; the fake curl probe answers by status code. No real secrets, no
containers and no InfluxDB requests are involved.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location(
    'verify_credential_restore',
    Path(__file__).resolve().parents[1] / 'scripts/verify-credential-restore.py')
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)

ORG_ID = '714f34e4c62e3500'
INFRA_ID = 'a1b2c3d4e5f60718'
WRITE_TOKEN = 'fixture-write-token-AAAA'
READ_TOKEN = 'fixture-read-token-BBBB'
FILES = {
    'threadripper-infra-token.json': {'auth_id': '0000000000000001', 'description': 'fixture write',
                                      'token': WRITE_TOKEN},
    'grafana-infra-token.json': {'auth_id': '0000000000000002', 'description': 'fixture read',
                                 'token': READ_TOKEN},
}


class FakeDocker:
    """Records every command; materialises restored files on `docker cp` out."""
    def __init__(self, files=FILES, write_code=b'400', read_code=b'200', fail_at=None):
        self.files, self.write_code, self.read_code, self.fail_at = files, write_code, read_code, fail_at
        self.calls, self.probe_inputs = [], []

    def __call__(self, args, input=None, timeout=300):
        args = list(args); self.calls.append(args)
        joined = ' '.join(args)
        if self.fail_at and self.fail_at in joined:
            raise RuntimeError('Command failed (docker), output withheld')
        if args[0] == 'whoami': return b'tester'
        if args[:2] == ['docker', 'run']: return b'container-id\n'
        if args[:2] == ['docker', 'inspect']:
            return json.dumps([{'HostConfig': {'NetworkMode': 'none', 'Binds': None}}]).encode()
        if args[:2] == ['docker', 'cp'] and args[2].endswith(':/restore/checkpoint/credentials'):
            target = Path(args[3]); target.mkdir()
            for label, content in self.files.items():
                (target / label).write_bytes(json.dumps(content).encode())
            return b''
        if 'influx org list' in joined: return json.dumps([{'name': 'home', 'id': ORG_ID}]).encode()
        if 'influx bucket list' in joined: return json.dumps([{'name': 'infra', 'id': INFRA_ID}]).encode()
        if 'snapshots' in args: return b'[{"id": "snap-older"}, {"id": "snap-latest"}]'
        if 'curl' in args:
            self.probe_inputs.append(input)
            return self.write_code if b'/api/v2/write' in input else self.read_code
        return b''


@contextlib.contextmanager
def drill(fake, missing_key=False, missing_repository=False):
    with tempfile.TemporaryDirectory() as tmp:
        checkpoint = Path(tmp) / 'checkpoint'
        if not missing_repository: (checkpoint / 'repository').mkdir(parents=True)
        key = Path(tmp) / 'key'
        if not missing_key: key.write_bytes(b'fixture-password')
        data = Path(tmp) / 'data'; data.mkdir()
        d._loaded_tokens.clear()
        out = io.StringIO()
        with mock.patch.object(d.r, 'command', fake), mock.patch.object(d, 'KEY', key), \
                mock.patch.object(d, 'DATA', data), contextlib.redirect_stdout(out):
            code = d.main(['--checkpoint', str(checkpoint)])
        yield code, out.getvalue(), data


class DrillTests(unittest.TestCase):
    def test_success_prints_only_safe_fields_and_exits_zero(self):
        fake = FakeDocker()
        with drill(fake) as (code, out, data):
            report = json.loads(out)
            self.assertEqual(list(data.iterdir()), [])  # temp directory removed
        self.assertEqual(code, 0)
        self.assertTrue(report['ok'])
        self.assertEqual(report['snapshot'], 'snap-latest')
        self.assertEqual(report['credentials'], [
            {'label': 'threadripper-infra-token.json', 'auth_id': '0000000000000001',
             'description': 'fixture write', 'probe_ok': True},
            {'label': 'grafana-infra-token.json', 'auth_id': '0000000000000002',
             'description': 'fixture read', 'probe_ok': True}])
        self.assertNotIn(WRITE_TOKEN, out); self.assertNotIn(READ_TOKEN, out)

    def test_restore_command_shape(self):
        fake = FakeDocker()
        with drill(fake): pass
        run = next(c for c in fake.calls if c[:2] == ['docker', 'run'])
        self.assertEqual(run[run.index('--network') + 1], 'none')
        self.assertIn('threadripper-validation', run)
        name = run[run.index('--name') + 1]
        restic = next(c for c in fake.calls if c[:3] == ['docker', 'exec', name] and 'restic restore' in c[-1])
        self.assertIn('restic check && restic restore latest --target /restore --verify '
                      '--include "/checkpoint/credentials/*-infra-token.json"', restic[-1])
        self.assertIn('RESTIC_PASSWORD_FILE=/password', restic[-1])
        copies_in = [c[3] for c in fake.calls if c[:2] == ['docker', 'cp'] and c[3].startswith(name + ':')]
        self.assertEqual(copies_in, [name + ':/repository', name + ':/password'])
        self.assertEqual(fake.calls[-1], ['docker', 'rm', '-f', '-v', name])

    def test_tokens_never_appear_in_process_arguments(self):
        fake = FakeDocker()
        with drill(fake): pass
        for call in fake.calls:
            self.assertNotIn(WRITE_TOKEN, ' '.join(call)); self.assertNotIn(READ_TOKEN, ' '.join(call))
        self.assertEqual(len(fake.probe_inputs), 2)
        self.assertTrue(any(WRITE_TOKEN.encode() in i for i in fake.probe_inputs))  # curl config on stdin

    def test_probe_failure_reports_false_and_exits_one(self):
        fake = FakeDocker(read_code=b'401')
        with drill(fake) as (code, out, data):
            report = json.loads(out)
            self.assertEqual(list(data.iterdir()), [])
        self.assertEqual(code, 1)
        self.assertFalse(report['ok'])
        self.assertEqual([c['probe_ok'] for c in report['credentials']], [True, False])

    def test_missing_file_in_snapshot_is_failure(self):
        fake = FakeDocker(files={'grafana-infra-token.json': FILES['grafana-infra-token.json']})
        with drill(fake) as (code, out, data):
            report = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(report['credentials'][0]['note'], 'not in snapshot')
        self.assertTrue(report['credentials'][1]['probe_ok'])

    def test_failure_mid_drill_still_removes_container_and_temp(self):
        fake = FakeDocker(fail_at='restic restore')
        with drill(fake) as (code, out, data):
            report = json.loads(out)
            self.assertEqual(list(data.iterdir()), [])
        self.assertEqual(code, 1)
        self.assertEqual(report['error'], 'RuntimeError')
        self.assertTrue(any(c[:3] == ['docker', 'rm', '-f'] for c in fake.calls))

    def test_missing_repository_or_key_refused_before_any_docker(self):
        for kwargs in (dict(missing_repository=True), dict(missing_key=True)):
            fake = FakeDocker()
            with drill(fake, **kwargs) as (code, out, data):
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(out)['error'], 'ValueError')
            self.assertEqual(fake.calls, [])

    def test_emit_guard_refuses_loaded_tokens(self):
        d._loaded_tokens.clear(); d._loaded_tokens.add('guarded-token-value')
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                d.emit('leak: guarded-token-value')
            d.emit('safe')
        d._loaded_tokens.clear()


if __name__ == '__main__':
    unittest.main()
