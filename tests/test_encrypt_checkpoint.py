"""Unit tests for scripts/encrypt-checkpoint.py with Docker calls mocked.

Fixture credential files live in a temporary root; no real secrets are read.
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
    'encrypt_checkpoint', Path(__file__).resolve().parents[1] / 'scripts/encrypt-checkpoint.py')
e = importlib.util.module_from_spec(spec); spec.loader.exec_module(e)

REQUIRED = ['.env', 'mosquitto/password.txt', 'secrets/influx-operator-token']
OPTIONAL = ['secrets/threadripper-infra-token.json', 'secrets/grafana-infra-token.json']
KEY_NAME = 'influx-restic-password'


def fake_command(args, input=None, timeout=300):
    if args[0] == 'whoami': return b'tester'
    if args[:2] == ['docker', 'exec'] and 'snapshots' in args: return b'[{"id": "snap-1"}]'
    return b''


@contextlib.contextmanager
def fixture(present):
    """Temporary repository root holding the named credential fixtures plus a
    verified source checkpoint; yields (root, destination, recorded calls)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / 'root'
        for relative in present:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture-' + relative.encode())
        source = Path(tmp) / 'source'; source.mkdir()
        (source / 'verification.json').write_bytes(b'{}')
        destination = Path(tmp) / 'destination'
        calls = []
        def record(args, input=None, timeout=300):
            calls.append(list(args)); return fake_command(args, input, timeout)
        argv = ['encrypt-checkpoint.py', '--source', str(source), '--destination', str(destination)]
        with mock.patch.object(e.r, 'ROOT', root), mock.patch.object(e.r, 'command', record), \
                mock.patch('sys.argv', argv), contextlib.redirect_stdout(io.StringIO()):
            yield root, destination, calls


def credential_copies(calls):
    """(source path, label) for every docker cp into /checkpoint/credentials/."""
    return [(c[2], c[3].split('/checkpoint/credentials/')[1]) for c in calls
            if c[:2] == ['docker', 'cp'] and '/checkpoint/credentials/' in c[3]]


class CredentialListTests(unittest.TestCase):
    def test_lists_infra_token_files_as_optional_with_expected_labels(self):
        entries = {relative: (label, required) for relative, label, required in e.CREDENTIALS}
        self.assertEqual(entries['secrets/threadripper-infra-token.json'],
                         ('threadripper-infra-token.json', False))
        self.assertEqual(entries['secrets/grafana-infra-token.json'],
                         ('grafana-infra-token.json', False))
        for relative in REQUIRED:
            self.assertTrue(entries[relative][1], relative)

    def test_never_lists_the_restic_password(self):
        for relative, label, _ in e.CREDENTIALS:
            self.assertNotIn(KEY_NAME, relative)
            self.assertNotIn(KEY_NAME, label)


class MainTests(unittest.TestCase):
    def test_required_file_missing_fails_and_removes_container(self):
        with fixture(REQUIRED[:-1] + OPTIONAL) as (root, destination, calls):
            with self.assertRaises(FileNotFoundError):
                e.main()
        self.assertFalse((destination / 'encryption-verification.json').exists())
        self.assertEqual(calls[-1][:3], ['docker', 'rm', '-f'])

    def test_optional_missing_is_recorded_skip(self):
        with fixture(REQUIRED) as (root, destination, calls):
            e.main()
            verification = json.loads((destination / 'encryption-verification.json').read_bytes())
        self.assertEqual(verification['credentials_included'],
                         ['iot.env', 'mosquitto-password.txt', 'influx-operator-token'])
        self.assertEqual(verification['credentials_skipped'],
                         ['threadripper-infra-token.json', 'grafana-infra-token.json'])
        self.assertEqual([label for _, label in credential_copies(calls)],
                         verification['credentials_included'])
        self.assertTrue(verification['all_data_checked'])
        self.assertEqual(verification['snapshot'], 'snap-1')

    def test_optional_present_are_copied_with_labels_and_listed(self):
        with fixture(REQUIRED + OPTIONAL) as (root, destination, calls):
            e.main()
            verification = json.loads((destination / 'encryption-verification.json').read_bytes())
        copies = credential_copies(calls)
        expected = ['iot.env', 'mosquitto-password.txt', 'influx-operator-token',
                    'threadripper-infra-token.json', 'grafana-infra-token.json']
        self.assertEqual([label for _, label in copies], expected)
        self.assertEqual(verification['credentials_included'], expected)
        self.assertEqual(verification['credentials_skipped'], [])
        self.assertEqual([Path(source).name for source, _ in copies[-2:]],
                         ['threadripper-infra-token.json', 'grafana-infra-token.json'])
        self.assertTrue(all(Path(source).is_relative_to(root) for source, _ in copies))

    def test_restic_password_is_never_copied_into_checkpoint(self):
        with fixture(REQUIRED + OPTIONAL) as (root, destination, calls):
            e.main()
            self.assertTrue((root / 'secrets' / KEY_NAME).is_file())  # generated by the script
        key_copies = [c for c in calls if c[:2] == ['docker', 'cp'] and KEY_NAME in c[2]]
        self.assertEqual([c[3].split(':', 1)[1] for c in key_copies], ['/password'])
        for source, label in credential_copies(calls):
            self.assertNotIn(KEY_NAME, source)
            self.assertNotIn(KEY_NAME, label)


if __name__ == '__main__':
    unittest.main()
