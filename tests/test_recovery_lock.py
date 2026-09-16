"""Regression tests for scripts/daily-recovery.py's OS-held exclusive lock.

These deliberately use REAL subprocess contention against the module's own
acquire_lock()/release_lock() -- a helper subprocess (spawned with
subprocess.Popen, importing daily-recovery.py fresh) actually takes the OS
lock (msvcrt.locking on Windows, fcntl.flock elsewhere) so that a competing
acquire in this test process faces genuine OS-level contention, not a mock
of the locking call. Everything runs under per-test temporary directories;
no network, no repository/production paths, no secrets are touched.

Covers the defect this module used to have: a live owner's lock could be
stolen once a file looked "old enough" or its owning PID looked dead, and
release_lock() unconditionally unlinked the lock file by pathname (which
could delete/unlock a lock a different process had since acquired). The new
design decides acquisition purely by whether the OS lock itself is held;
age and pid/started_at/hostname metadata are informational only.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

MOD_PATH = Path(__file__).resolve().parents[1] / 'scripts/daily-recovery.py'

spec = importlib.util.spec_from_file_location('daily_recovery', MOD_PATH)
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)

try:
    if sys.platform == 'win32':
        import msvcrt  # noqa: F401
    else:
        import fcntl  # noqa: F401
    HAVE_OS_LOCK_PRIMITIVE = True
except ImportError:
    HAVE_OS_LOCK_PRIMITIVE = False


# A helper subprocess that imports daily-recovery.py fresh and calls its real
# acquire_lock()/release_lock(). Writing `ready_file` only after the OS lock
# is actually held lets the parent test know contention is now genuine.
# `result_file`, if given, records OK/FAIL for the concurrent-acquisition
# test; the helper's own exit code mirrors this (0 = acquired, 3 = refused).
HELPER_SRC = r'''
import importlib.util, sys, time
from pathlib import Path

mod_path = sys.argv[1]
dest = Path(sys.argv[2])
ready_file = Path(sys.argv[3])
hold_seconds = float(sys.argv[4])
result_file = Path(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else None

spec = importlib.util.spec_from_file_location('daily_recovery_lock_helper', mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

try:
    handle = mod.acquire_lock(dest)
except mod.LockHeld:
    if result_file is not None:
        result_file.write_text('FAIL')
    sys.exit(3)

if result_file is not None:
    result_file.write_text('OK')
ready_file.write_text('ready')
time.sleep(hold_seconds)
mod.release_lock(handle)
sys.exit(0)
'''


def spawn_helper(dest, ready_file, hold_seconds, result_file=None):
    args = [sys.executable, '-c', HELPER_SRC, str(MOD_PATH), str(dest), str(ready_file), str(hold_seconds)]
    args.append(str(result_file) if result_file is not None else '')
    return subprocess.Popen(args)


def wait_for_file(path, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return False


def write_metadata(lock_path, payload_dict):
    """Overwrite only the informational metadata region (after the reserved
    marker byte) -- never byte 0, which is the actual OS-locked byte, so this
    is safe to call from a process that does not hold the lock even under
    Windows' mandatory byte-range locking."""
    payload = json.dumps(payload_dict).encode()
    with open(lock_path, 'r+b') as fh:
        fh.seek(d._LOCK_MARKER_BYTES)
        fh.write(payload)
        fh.truncate(d._LOCK_MARKER_BYTES + len(payload))


def truncate_metadata(lock_path):
    """Blank the metadata region back to empty while leaving the reserved
    marker byte (and hence any real OS lock on it) untouched."""
    with open(lock_path, 'r+b') as fh:
        fh.truncate(d._LOCK_MARKER_BYTES)


@unittest.skipUnless(HAVE_OS_LOCK_PRIMITIVE, 'platform has no supported OS lock primitive')
class RecoveryLockTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dest = Path(self._tmp.name) / 'dest'
        self.dest.mkdir(parents=True)
        self._procs = []

    def tearDown(self):
        for proc in self._procs:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)

    def spawn(self, ready_file, hold_seconds, result_file=None):
        proc = spawn_helper(self.dest, ready_file, hold_seconds, result_file)
        self._procs.append(proc)
        return proc

    # (a) live aged owner: a genuinely live holder must never be stolen from
    # just because the lock file/metadata looks old.
    def test_live_aged_owner_blocks_second_acquire(self):
        ready = self.dest / 'ready'
        self.spawn(ready, hold_seconds=6.0)
        self.assertTrue(wait_for_file(ready), 'helper did not signal ready in time')

        lock_path = self.dest / d.LOCK_NAME
        old_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        write_metadata(lock_path, dict(pid=999999999, started_at=old_iso, hostname='someone-else'))
        old_ts = time.time() - 7200
        os.utime(lock_path, (old_ts, old_ts))

        with self.assertRaises(d.LockHeld):
            d.acquire_lock(self.dest)

    # (b) partial initialization: unreadable/empty metadata while the real OS
    # lock is held must never be read as "safe to take over".
    def test_partial_initialization_metadata_blocks_second_acquire(self):
        ready = self.dest / 'ready'
        self.spawn(ready, hold_seconds=6.0)
        self.assertTrue(wait_for_file(ready), 'helper did not signal ready in time')

        lock_path = self.dest / d.LOCK_NAME
        truncate_metadata(lock_path)  # metadata region now empty; marker byte (the lock) untouched

        with self.assertRaises(d.LockHeld):
            d.acquire_lock(self.dest)

    # (c) concurrent acquisition: of N simultaneous real attempts, exactly
    # one may succeed.
    def test_concurrent_acquisition_exactly_one_winner(self):
        n = 5
        readies = [self.dest / ('ready-%d' % i) for i in range(n)]
        results = [self.dest / ('result-%d' % i) for i in range(n)]
        procs = [self.spawn(readies[i], hold_seconds=2.0, result_file=results[i]) for i in range(n)]

        for proc in procs:
            proc.wait(timeout=15)

        outcomes = [r.read_text() if r.exists() else 'MISSING' for r in results]
        self.assertEqual(outcomes.count('OK'), 1, 'exactly one of %d concurrent acquirers must win: %r' % (n, outcomes))
        self.assertEqual(outcomes.count('FAIL'), n - 1)
        return_codes = sorted(p.returncode for p in procs)
        self.assertEqual(return_codes, sorted([0] + [3] * (n - 1)))

    # (d) abandoned owner: a killed holder's lock must be recoverable with no
    # manual cleanup of any kind.
    def test_abandoned_owner_recovers_without_manual_cleanup(self):
        ready = self.dest / 'ready'
        proc = self.spawn(ready, hold_seconds=120.0)
        self.assertTrue(wait_for_file(ready), 'helper did not signal ready in time')
        proc.kill()
        proc.wait(timeout=10)

        lock_path = self.dest / d.LOCK_NAME
        self.assertTrue(lock_path.exists(), 'the lock file itself must still exist; nothing is unlinked')

        handle = d.acquire_lock(self.dest)  # must not raise
        try:
            self.assertIsInstance(handle, d.LockHandle)
        finally:
            d.release_lock(handle)

    # (e) release after ownership change: a stale handle (or a second
    # release from the same one) must never affect a lock a different owner
    # has since acquired.
    def test_release_after_ownership_change_does_not_affect_new_owner(self):
        handle_a = d.acquire_lock(self.dest)
        d.release_lock(handle_a)

        ready_b = self.dest / 'ready-b'
        proc_b = self.spawn(ready_b, hold_seconds=6.0)
        self.assertTrue(wait_for_file(ready_b), 'owner B did not signal ready in time')

        # A's stale handle, and a second release of it, must be no-ops.
        d.release_lock(handle_a)

        # B's lock must still block a third acquirer (this test process,
        # genuinely distinct from B's subprocess).
        with self.assertRaises(d.LockHeld):
            d.acquire_lock(self.dest)


if __name__ == '__main__':
    unittest.main()
