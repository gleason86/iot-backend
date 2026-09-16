"""Unit tests for scripts/daily-recovery.py with subprocess.run fully mocked.

No real Docker, SSH, scp or host disk state is touched: ROOT and DEST are
patched to per-test temporary directories, disk-usage is patched, and time is
frozen so the run's stamp/paths are deterministic. Fixture "subprocess" calls
simulate just enough of influx-recovery.py/encrypt-checkpoint.py/
mqtt-recovery.py's real side effects (creating their expected output files)
for the pipeline logic in main() to run end to end.

Every test drives the script through `cli_main()` (the real script entry
point) rather than calling `main()` directly, and asserts on the resulting
`SystemExit` code as well as status/latest file contents, per the
failure-injection requirements this module is meant to cover:
cleanup denial, malformed MQTT response (four variants), missing/unreadable
Influx archive, capacity failure, subprocess timeout, atomic-write failure,
overlapping run (lock held), and the all-success path.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile as tarfile_module
import tempfile
import time
import unittest
from unittest import mock

MOD_PATH = Path(__file__).resolve().parents[1] / 'scripts/daily-recovery.py'
spec = importlib.util.spec_from_file_location('daily_recovery', MOD_PATH)
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)

STAMP = '20260101T000000Z'
MQTT_STAMP = '20260101T000030Z'  # deliberately different from STAMP: mqtt-recovery.py
                                  # generates its own independent timestamp.

# A real subprocess that imports daily-recovery.py fresh and calls its real
# acquire_lock()/release_lock() -- used so the two lock tests below exercise
# genuine OS-level contention (a second live process really holding the lock)
# rather than a plain file that happens to exist, which the new OS-lock
# semantics no longer treat as a conflict by itself.
LOCK_HELPER_SRC = r'''
import importlib.util, sys, time
from pathlib import Path

mod_path, dest, ready_file, hold_seconds = (
    sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), float(sys.argv[4]))

spec = importlib.util.spec_from_file_location('daily_recovery_lock_helper', mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

handle = mod.acquire_lock(dest)
ready_file.write_text('ready')
time.sleep(hold_seconds)
mod.release_lock(handle)
'''


def spawn_lock_helper(dest, ready_file, hold_seconds):
    return subprocess.Popen([sys.executable, '-c', LOCK_HELPER_SRC,
                              str(MOD_PATH), str(dest), str(ready_file), str(hold_seconds)])


def wait_for_file(path, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return False


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 1, 1, tzinfo=timezone.utc)


def completed(args, returncode=0, stdout=b'', stderr=b''):
    return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr=stderr)


def make_fake_run(root, dest, mqtt_archive, fail=None, mqtt_response=None):
    """`fail` is (predicate(args, joined) -> bool, mode, payload) or None.
    `mode` is an int returncode, or the string 'timeout' to raise
    subprocess.TimeoutExpired instead. The matched call fails/times out;
    every other recognised call succeeds and performs the minimal filesystem
    side effect main() depends on. `mqtt_response`, if given, replaces the
    default well-formed JSON stdout from the mqtt-recovery.py call."""
    source = root / 'data' / ('daily-' + STAMP)
    checkpoint_dest = dest / STAMP

    def fake(args, capture_output=True, timeout=None, stdin=None):
        joined = ' '.join(str(a) for a in args)
        if fail and fail[0](args, joined):
            if fail[1] == 'timeout':
                raise subprocess.TimeoutExpired(cmd=args, timeout=timeout or 600, output=b'', stderr=fail[2])
            return completed(args, fail[1], stderr=fail[2])
        if args[0] == sys.executable and 'influx-recovery.py' in joined:
            source.mkdir(parents=True, exist_ok=True)
            (source / 'verification.json').write_bytes(b'{}')
            return completed(args)
        if args[0] == sys.executable and 'encrypt-checkpoint.py' in joined:
            (checkpoint_dest / 'repository').mkdir(parents=True, exist_ok=True)
            (checkpoint_dest / 'repository' / 'pack').write_bytes(b'restic-pack')
            (checkpoint_dest / 'encryption-verification.json').write_bytes(b'{}')
            return completed(args)
        if args[0] == sys.executable and 'mqtt-recovery.py' in joined:
            if mqtt_response is not None:
                return completed(args, stdout=mqtt_response)
            return completed(args, stdout=json.dumps({'archive': str(mqtt_archive)}).encode())
        if args[0] == 'ssh' and 'sha256sum' in joined:
            target = mqtt_archive if 'mqtt-' in joined else checkpoint_dest / 'encrypted.tar'
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            return completed(args, stdout=(digest + '  remote.part\n').encode())
        # budget-check ssh, scp (both archives) and the final ssh mv: no-ops.
        return completed(args)
    return fake


class DailyRecoveryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.root = base / 'root'
        self.dest = base / 'dest'
        (self.root / 'data').mkdir(parents=True)
        self.dest.mkdir(parents=True)
        mqtt_dir = self.dest / ('mqtt-' + MQTT_STAMP)
        mqtt_dir.mkdir(parents=True)
        self.mqtt_archive = mqtt_dir / 'encrypted.tar'
        self.mqtt_archive.write_bytes(b'mqtt-fixture-bytes')

        self._patches = [
            mock.patch.object(d, 'ROOT', self.root),
            mock.patch.object(d, 'DEST', self.dest),
            mock.patch.object(d, 'datetime', FixedDatetime),
            mock.patch.object(d.shutil, 'disk_usage',
                               return_value=type('U', (), {'total': 0, 'used': 0, 'free': 100 * 1024**3})()),
        ]
        for p in self._patches:
            p.start(); self.addCleanup(p.stop)

    def run_cli(self, fail=None, mqtt_response=None, extra_patches=()):
        fake = make_fake_run(self.root, self.dest, self.mqtt_archive, fail=fail, mqtt_response=mqtt_response)
        patches = [mock.patch.object(d.subprocess, 'run', side_effect=fake),
                   mock.patch('sys.argv', ['daily-recovery.py'])] + list(extra_patches)
        for p in patches:
            p.start()
        try:
            out = io.StringIO()
            code = 0
            with mock.patch('sys.stdout', out):
                try:
                    d.cli_main()
                except SystemExit as exc:
                    code = exc.code
            return out.getvalue(), code
        finally:
            for p in reversed(patches):
                p.stop()

    def staging_dir(self):
        return self.root / 'data' / ('daily-' + STAMP)

    def read_json(self, name):
        return json.loads((self.dest / name).read_bytes())

    def exists(self, name):
        return (self.dest / name).exists()


class AllSuccessTests(DailyRecoveryTests):
    def test_all_stages_succeed(self):
        out, code = self.run_cli()
        self.assertEqual(code, 0)
        latest = self.read_json('latest.json')
        latest_influx = self.read_json('latest-influx.json')
        status = self.read_json('status.json')

        self.assertEqual(latest['overall'], 'success')
        self.assertNotIn('failing_stage', latest)
        self.assertTrue(latest['native_restore_verified'])
        self.assertTrue(latest['mqtt_restore_verified'])
        self.assertEqual(latest['mqtt_independent_copy'],
                         '/home/david/iot-checkpoints/mqtt-' + STAMP + '.tar')
        self.assertEqual(latest_influx['sha256'], latest['sha256'])

        self.assertEqual(status['overall'], 'success')
        self.assertTrue(all(s['status'] == 'ok' for s in status['stages'].values()))
        self.assertEqual(set(status['stages']), set(d.STAGES))

        self.assertFalse(self.staging_dir().exists(), 'decrypted staging must be removed on success')
        # The lock file itself is kept (never unlinked); "released" means the
        # OS lock is gone, which we verify by successfully re-acquiring it.
        self.assertTrue((self.dest / d.LOCK_NAME).exists(), 'lock file itself must be kept, not unlinked')
        reacquired = d.acquire_lock(self.dest)
        d.release_lock(reacquired)
        self.assertEqual(json.loads(out), latest)


class MqttFailureTests(DailyRecoveryTests):
    def test_mqtt_export_subprocess_failure_leaves_latest_untouched_but_persists_influx(self):
        secret = 'token=SUPERSECRETVALUE1234567890ABCDEF'

        def match(args, joined):
            return args[0] == sys.executable and 'mqtt-recovery.py' in joined
        out, code = self.run_cli(fail=(match, 1, ('mqtt export blew up: ' + secret).encode()))
        self.assertNotEqual(code, 0)

        self.assertFalse(self.exists('latest.json'), 'not a full success: latest.json must not be written')
        latest_influx = self.read_json('latest-influx.json')
        self.assertTrue(latest_influx['native_restore_verified'])
        status = self.read_json('status.json')

        self.assertEqual(status['overall'], 'partial')
        for name in ('preflight', 'influx_backup', 'encrypt', 'tar', 'offhost_copy', 'cleanup'):
            self.assertEqual(status['stages'][name]['status'], 'ok')
        self.assertEqual(status['stages']['mqtt_export']['status'], 'failed')
        self.assertEqual(status['stages']['mqtt_export']['exit_code'], 1)
        self.assertEqual(status['stages']['mqtt_copy']['status'], 'pending')

        # mqtt_export is a credential-bearing stage: no raw stderr tail exposed.
        self.assertNotIn('stderr_tail', status['stages']['mqtt_export'])
        self.assertIn('description', status['stages']['mqtt_export'])

        raw = (self.dest / 'status.json').read_bytes()
        self.assertNotIn(b'SUPERSECRETVALUE1234567890ABCDEF', raw)
        self.assertNotIn('SUPERSECRETVALUE1234567890ABCDEF', out)

        self.assertFalse(self.staging_dir().exists(),
                          'Influx off-host copy is verified before MQTT runs; staging must still be removed')

    def test_mqtt_copy_failure_also_yields_partial_and_keeps_influx_evidence(self):
        def match(args, joined):
            return args[0] == 'scp' and 'mqtt-' in joined
        out, code = self.run_cli(fail=(match, 1, b'scp: connection refused'))
        self.assertNotEqual(code, 0)
        self.assertFalse(self.exists('latest.json'))
        self.assertTrue(self.exists('latest-influx.json'))
        status = self.read_json('status.json')
        self.assertEqual(status['stages']['mqtt_export']['status'], 'ok')
        self.assertEqual(status['stages']['mqtt_copy']['status'], 'failed')
        # mqtt_copy is not credential-bearing: a redacted tail is allowed.
        self.assertIn('stderr_tail', status['stages']['mqtt_copy'])
        self.assertFalse(self.staging_dir().exists())


class MalformedMqttResponseTests(DailyRecoveryTests):
    def _assert_mqtt_export_validation_failure(self, out, code, reason_snippet):
        self.assertNotEqual(code, 0)
        self.assertFalse(self.exists('latest.json'))
        self.assertTrue(self.exists('latest-influx.json'), 'Influx side already succeeded independently')
        status = self.read_json('status.json')
        self.assertEqual(status['stages']['mqtt_export']['status'], 'failed')
        self.assertNotIn('stderr_tail', status['stages']['mqtt_export'])
        self.assertIn('description', status['stages']['mqtt_export'])
        self.assertEqual(status['stages']['mqtt_copy']['status'], 'pending')

    def test_non_json_response(self):
        out, code = self.run_cli(mqtt_response=b'not json at all')
        self._assert_mqtt_export_validation_failure(out, code, 'invalid JSON')

    def test_missing_archive_key(self):
        out, code = self.run_cli(mqtt_response=json.dumps({'report': {}}).encode())
        self._assert_mqtt_export_validation_failure(out, code, 'missing')

    def test_archive_outside_expected_directory(self):
        outside = self.root / 'evil' / 'encrypted.tar'
        outside.parent.mkdir(parents=True)
        outside.write_bytes(b'not really the mqtt archive')
        out, code = self.run_cli(mqtt_response=json.dumps({'archive': str(outside)}).encode())
        self._assert_mqtt_export_validation_failure(out, code, 'outside expected directory')

    def test_unreadable_archive(self):
        # A directory where a file is expected is a portable stand-in for
        # "unreadable" that does not depend on platform permission semantics:
        # the well-formed path passes containment/naming validation but
        # fails when daily-recovery.py tries to open() it as a file.
        self.mqtt_archive.unlink()
        self.mqtt_archive.mkdir()
        out, code = self.run_cli(mqtt_response=json.dumps({'archive': str(self.mqtt_archive)}).encode())
        self._assert_mqtt_export_validation_failure(out, code, 'unreadable')


class InfluxFailureTests(DailyRecoveryTests):
    def test_influx_backup_failure_leaves_latest_untouched_and_retains_staging(self):
        sentinel = json.dumps({'overall': 'success', 'sentinel': True}).encode() + b'\n'
        (self.dest / 'latest.json').write_bytes(sentinel)

        def match(args, joined):
            return args[0] == sys.executable and 'influx-recovery.py' in joined
        out, code = self.run_cli(fail=(match, 2, b'influx backup failed: disk full'))
        self.assertNotEqual(code, 0)

        self.assertEqual((self.dest / 'latest.json').read_bytes(), sentinel,
                         'an earlier-stage failure must never touch latest.json')
        self.assertFalse(self.exists('latest-influx.json'), 'checkpoint was never verified this run')

        status = self.read_json('status.json')
        self.assertEqual(status['overall'], 'failed')
        self.assertEqual(status['failing_stage'], 'influx_backup')
        self.assertEqual(status['stages']['influx_backup']['status'], 'failed')
        self.assertEqual(status['stages']['influx_backup']['exit_code'], 2)
        # influx_backup is credential-bearing: no raw stderr tail exposed.
        self.assertNotIn('stderr_tail', status['stages']['influx_backup'])
        for name in ('encrypt', 'tar', 'offhost_copy', 'cleanup', 'mqtt_export', 'mqtt_copy'):
            self.assertEqual(status['stages'][name]['status'], 'pending')

    def test_encrypt_failure_never_exposes_stderr_tail(self):
        secret = 'password=hunterhunterhunterhunterhunterhunter2'

        def match(args, joined):
            return args[0] == sys.executable and 'encrypt-checkpoint.py' in joined
        out, code = self.run_cli(fail=(match, 1, secret.encode()))
        self.assertNotEqual(code, 0)
        status = self.read_json('status.json')
        self.assertEqual(status['stages']['encrypt']['status'], 'failed')
        self.assertNotIn('stderr_tail', status['stages']['encrypt'])
        raw = (self.dest / 'status.json').read_bytes()
        self.assertNotIn(b'hunterhunterhunterhunterhunterhunter2', raw)
        self.assertNotIn('hunterhunterhunterhunterhunterhunter2', out)

    def test_offhost_copy_failure_retains_staging_for_diagnosis(self):
        """A later Influx-side failure (after real backup content exists) is
        the meaningful case for 'staging retained for diagnosis': cleanup
        only ever happens once the off-host copy stage itself succeeds."""
        def match(args, joined):
            return args[0] == 'scp' and 'mqtt-' not in joined
        out, code = self.run_cli(fail=(match, 1, b'scp: no route to host'))
        self.assertNotEqual(code, 0)

        self.assertFalse(self.exists('latest.json'))
        self.assertFalse(self.exists('latest-influx.json'), 'checksum was never verified')
        self.assertTrue(self.staging_dir().is_dir(), 'staging must be retained when offhost_copy fails')
        self.assertTrue((self.staging_dir() / 'verification.json').is_file())

        status = self.read_json('status.json')
        self.assertEqual(status['overall'], 'failed')
        self.assertEqual(status['stages']['offhost_copy']['status'], 'failed')
        self.assertEqual(status['stages']['tar']['status'], 'ok')

    def test_missing_influx_archive_at_hash_time(self):
        """Simulate the archive going missing between a successful tar stage
        and the hashing step that immediately follows it inside offhost_copy."""
        real_open = tarfile_module.open

        def vanishing_open(path, mode='w'):
            cm = real_open(path, mode)
            class Wrapper:
                def __enter__(self_):
                    self_.inner = cm.__enter__()
                    return self_.inner
                def __exit__(self_, exc_type, exc, tb):
                    result = cm.__exit__(exc_type, exc, tb)
                    if exc_type is None:
                        Path(path).unlink()
                    return result
            return Wrapper()

        out, code = self.run_cli(extra_patches=[mock.patch.object(d.tarfile, 'open', side_effect=vanishing_open)])
        self.assertNotEqual(code, 0)
        self.assertFalse(self.exists('latest.json'))
        self.assertFalse(self.exists('latest-influx.json'), 'checksum never computed: archive vanished first')
        status = self.read_json('status.json')
        self.assertEqual(status['stages']['tar']['status'], 'ok', 'tar itself succeeded before the file vanished')
        self.assertEqual(status['stages']['offhost_copy']['status'], 'failed')


class CapacityFailureTests(DailyRecoveryTests):
    def test_free_space_reserve_reached(self):
        low_disk = mock.patch.object(d.shutil, 'disk_usage',
                                       return_value=type('U', (), {'total': 0, 'used': 0, 'free': 1})())
        out, code = self.run_cli(extra_patches=[low_disk])
        self.assertNotEqual(code, 0)
        self.assertFalse(self.exists('latest.json'))
        self.assertFalse(self.exists('latest-influx.json'))
        status = self.read_json('status.json')
        self.assertEqual(status['overall'], 'failed')
        self.assertEqual(status['failing_stage'], 'preflight')
        self.assertEqual(status['stages']['preflight']['status'], 'failed')
        self.assertNotIn('stderr_tail', status['stages']['preflight'])
        for name in ('influx_backup', 'encrypt', 'tar', 'offhost_copy', 'cleanup', 'mqtt_export', 'mqtt_copy'):
            self.assertEqual(status['stages'][name]['status'], 'pending')


class TimeoutTests(DailyRecoveryTests):
    def test_influx_backup_subprocess_timeout(self):
        secret = 'token=SHOULDNOTLEAK1234567890ABCDEFGHIJ'

        def match(args, joined):
            return args[0] == sys.executable and 'influx-recovery.py' in joined
        out, code = self.run_cli(fail=(match, 'timeout', secret.encode()))
        self.assertNotEqual(code, 0)
        status = self.read_json('status.json')
        self.assertEqual(status['stages']['influx_backup']['status'], 'failed')
        self.assertEqual(status['stages']['influx_backup']['exit_code'], 'timeout')
        self.assertNotIn('stderr_tail', status['stages']['influx_backup'])
        raw = (self.dest / 'status.json').read_bytes()
        self.assertNotIn(b'SHOULDNOTLEAK1234567890ABCDEFGHIJ', raw)


class CleanupFailureTests(DailyRecoveryTests):
    def test_cleanup_denial_preserves_influx_evidence_and_still_runs_mqtt(self):
        rmtree_patch = mock.patch.object(d.shutil, 'rmtree', side_effect=PermissionError('denied'))
        out, code = self.run_cli(extra_patches=[rmtree_patch])
        self.assertNotEqual(code, 0, 'cleanup failure means this is not a full success')

        self.assertFalse(self.exists('latest.json'), 'not a full success: cleanup failed')
        latest_influx = self.read_json('latest-influx.json')
        self.assertTrue(latest_influx['native_restore_verified'],
                        'Influx evidence must survive a cleanup failure')

        status = self.read_json('status.json')
        self.assertEqual(status['stages']['cleanup']['status'], 'failed')
        self.assertIn('stderr_tail', status['stages']['cleanup'])  # cleanup carries no credentials
        self.assertIn('denied', status['stages']['cleanup']['stderr_tail'])
        # Cleanup failing must not block the MQTT stages from being attempted.
        self.assertEqual(status['stages']['mqtt_export']['status'], 'ok')
        self.assertEqual(status['stages']['mqtt_copy']['status'], 'ok')
        self.assertEqual(status['overall'], 'partial')
        self.assertEqual(status['failing_stage'], 'cleanup')


class AtomicWriteFailureTests(DailyRecoveryTests):
    def test_final_latest_json_replace_failure_yields_sanitized_summary_no_traceback(self):
        real_replace = os.replace

        def flaky_replace(src, dst):
            if Path(dst).name == 'latest.json':
                raise OSError('simulated os.replace failure for latest.json')
            return real_replace(src, dst)

        out, code = self.run_cli(extra_patches=[mock.patch.object(d.os, 'replace', side_effect=flaky_replace)])
        self.assertNotEqual(code, 0)
        self.assertFalse(self.exists('latest.json'))
        # Written earlier in the pipeline, unaffected by the later latest.json failure.
        self.assertTrue(self.exists('latest-influx.json'))

        status = self.read_json('status.json')
        self.assertEqual(status['overall'], 'error')
        self.assertIn('OSError', status['error'])
        self.assertNotIn('Traceback', status['error'])
        self.assertNotIn('Traceback', out)
        # No raw traceback should have reached stdout either.
        self.assertNotIn('  File "', out)


class LockTests(DailyRecoveryTests):
    """These drive real subprocess contention against the real
    acquire_lock()/release_lock() (only subprocess.run -- the pipeline's own
    external commands -- is mocked by run_cli(); the lock's OS-level
    primitives are untouched), because the new semantics decide acquisition
    purely by whether the OS lock is actually held by a live process. A lock
    *file* that merely exists, with no live holder, is no longer a conflict
    by itself -- unlike the old PID/age-based check this replaces."""

    def test_overlapping_run_is_refused_without_touching_status(self):
        ready = self.dest / 'lock-helper-ready'
        proc = spawn_lock_helper(self.dest, ready, hold_seconds=5.0)
        try:
            self.assertTrue(wait_for_file(ready, 10.0), 'lock helper did not signal ready in time')
            sentinel_status = b'{"sentinel": true}\n'
            (self.dest / 'status.json').write_bytes(sentinel_status)

            out, code = self.run_cli()
            self.assertNotEqual(code, 0)
            self.assertEqual((self.dest / 'status.json').read_bytes(), sentinel_status,
                             'a live conflicting lock must not touch the running instance\'s status.json')
            self.assertFalse(self.staging_dir().exists(), 'pipeline must never start when the lock is held')
            conflict = self.read_json('lock-conflict.json')
            self.assertEqual(conflict['overall'], 'skipped')
            self.assertEqual(conflict['reason'], 'lock_held')
        finally:
            proc.kill()
            proc.wait(timeout=10)

    def test_abandoned_owner_recovers_without_manual_unlink(self):
        """Replaces the old "stale lock is unlinked after LOCK_STALE_SECONDS"
        test: a lock owner that dies abnormally (killed, crashed, power loss)
        must be recoverable without deleting anything. The OS drops the held
        lock automatically when the killed process's file descriptor is torn
        down, so the very next acquire simply succeeds -- age is irrelevant,
        and no unlink of the lock file ever happens."""
        ready = self.dest / 'lock-helper-ready'
        proc = spawn_lock_helper(self.dest, ready, hold_seconds=120.0)
        self.assertTrue(wait_for_file(ready, 10.0), 'lock helper did not signal ready in time')
        proc.kill()
        proc.wait(timeout=10)

        lock_path = self.dest / d.LOCK_NAME
        self.assertTrue(lock_path.exists(), 'the abandoned lock file itself must still be present (never unlinked)')

        out, code = self.run_cli()
        self.assertEqual(code, 0, 'an abandoned (killed) owner must be recoverable without manual cleanup')
        latest = self.read_json('latest.json')
        self.assertEqual(latest['overall'], 'success')


class RedactionTests(unittest.TestCase):
    def test_keyword_values_are_redacted(self):
        text = ('token=ABCDEF0123456789ABCDEF0123456789 '
                'password: hunterhunterhunterhunterhunter2 '
                'Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345')
        redacted = d.redact(text)
        self.assertNotIn('ABCDEF0123456789ABCDEF0123456789', redacted)
        self.assertNotIn('hunterhunterhunterhunterhunter2', redacted)
        self.assertNotIn('abcdefghijklmnopqrstuvwxyz012345', redacted)
        self.assertIn('token=[redacted]', redacted)
        self.assertIn('password=[redacted]', redacted)
        self.assertIn('Authorization=[redacted]', redacted)

    def test_long_base64_or_hex_runs_are_redacted_even_without_a_keyword(self):
        text = 'unexpected bare value 9f8e7d6c5b4a3928170695867544332211aabbccddeeff00 in output'
        redacted = d.redact(text)
        self.assertNotIn('9f8e7d6c5b4a3928170695867544332211aabbccddeeff00', redacted)
        self.assertIn('[redacted]', redacted)

    def test_short_values_are_left_alone(self):
        text = 'exit status 1, retry count=3'
        self.assertEqual(d.redact(text), text)

    def test_stagefailure_tail_is_redacted_and_truncated(self):
        many_lines = '\n'.join('line %d' % i for i in range(30))
        stderr = (many_lines + '\ntoken=ZZZZ0123456789ZZZZ0123456789ZZZZ\n').encode()
        exc = d.StageFailure('encrypt', 1, stderr)
        self.assertNotIn('ZZZZ0123456789ZZZZ0123456789ZZZZ', exc.tail)
        self.assertIn('[redacted]', exc.tail)
        self.assertLessEqual(len(exc.tail.splitlines()), 20)


class MarkFailedAllowlistTests(unittest.TestCase):
    def test_tail_only_kept_for_allowlisted_stages(self):
        status = d.new_status()
        d.mark_failed(status, 'offhost_copy', 1, tail='safe tail text')
        self.assertEqual(status['offhost_copy']['stderr_tail'], 'safe tail text')

        status2 = d.new_status()
        d.mark_failed(status2, 'influx_backup', 1, tail='token=abc123... should never surface')
        self.assertNotIn('stderr_tail', status2['influx_backup'])
        self.assertIn('description', status2['influx_backup'])


if __name__ == '__main__':
    unittest.main()
