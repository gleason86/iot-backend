"""Daily online export, isolated restore, encryption and independent host copy.

No live restart, endpoint change, retention deletion or standby refresh/promotion.
Requires the owner's existing Docker Desktop, SSH access and protected key.

Per-stage status is recorded to D:/Backups/iot-backend/status.json on every exit
path, including preflight capacity checks, staging cleanup, and MQTT result
validation/hashing -- every path in the pipeline is now inside stage/status
handling, so a failure anywhere produces a truthful status entry instead of an
unhandled traceback.

Checkpoint history has two files with distinct meaning, chosen after checking
this repo, threadripper and grafana for programmatic consumers of these paths:
none were found (only prose in docs refers to them), so this run is free to
split them without breaking an existing reader:
  * `latest-influx.json` is rewritten as soon as the Influx checkpoint's
    off-host copy checksum is independently verified -- before staging cleanup
    and before any MQTT work -- and is the newest verified Influx checkpoint,
    full stop, regardless of what happens afterward.
  * `latest.json` is written only when the *entire* pipeline (through the
    final MQTT copy) succeeds. It is never written for a partial run, so a
    consumer cannot mistake a stale `latest.json`'s `completed_at` for a signal
    that today's run was fully successful -- an absent/stale `latest.json`
    combined with a fresh `latest-influx.json` and `status.json` overall
    "partial" is the truthful signal.

Cleanup (removing the decrypted staging directory) is its own stage; a cleanup
failure is recorded but does not erase the already-persisted Influx evidence
and does not block the MQTT stages from running.

An in-script exclusive lock (`D:/Backups/iot-backend/daily-recovery.lock`)
refuses overlapping manual/scheduled executions. Acquisition is decided
entirely by an OS-held lock on the file (`msvcrt.locking` on Windows,
`fcntl.flock` elsewhere), taken for the whole run: the file's age and its
pid/started_at/hostname metadata (written only *after* the OS lock is held)
are informational only and never grant takeover, so a live owner's lock is
never stolen just because time passed, or because its metadata was briefly
missing or unreadable during that owner's own initialization. Releasing the
lock only unlocks and closes this process's own descriptor -- it never
unlinks the lock file by pathname, so it cannot remove or unlock a lock a
*different* process has since acquired on the same path; a second release, or
a release from a handle that never actually acquired, is a no-op. On abnormal
exit (crash, kill, power loss) the OS drops the lock automatically when the
process's descriptor is torn down, so the next run's acquire simply succeeds
-- that is the documented, safe recovery path for an abandoned lock; no
manual unlink of `daily-recovery.lock` is needed, or ever performed, by this
script.

Stage failure evidence favors small, allowlisted descriptions over raw
subprocess output. A stderr tail (redacted, capped at 20 lines) is only kept
for stages whose underlying commands are known not to handle credentials
(tar, offhost_copy, cleanup, mqtt_copy); the influx_backup, encrypt and
mqtt_export stages invoke scripts that read tokens/passwords, so their status
entries carry only a stage name, exit code and fixed description. Redaction is
kept as defense in depth on whatever tails are allowed through.

Report writes (status.json, latest.json, latest-influx.json, lock-conflict.json)
are atomic: written to a temp file and moved into place with `os.replace`. Any
unexpected exception -- including a report-write failure itself -- is caught by
`cli_main()` and turned into a sanitized summary plus a non-zero exit; no raw
traceback is ever allowed to reach stdout/stderr when run as a script.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time

if sys.platform == 'win32':
    import msvcrt
else:
    import fcntl

ROOT = Path(__file__).resolve().parents[1]
DEST = Path('D:/Backups/iot-backend')
SSH = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15',
       '-o', 'ServerAliveCountMax=2', '-o', 'HostKeyAlias=192.168.1.105']
HOST = 'david@192.168.1.106'

# Stage order matches the pipeline in main(); every run's status.json/report
# accounts for all eight, marking any stage not reached "pending".
STAGES = ('preflight', 'influx_backup', 'encrypt', 'tar', 'offhost_copy',
          'cleanup', 'mqtt_export', 'mqtt_copy')

# Stages whose underlying commands are known not to handle credentials: a
# redacted stderr tail may be kept for these. influx_backup/encrypt/mqtt_export
# invoke scripts that read Influx/restic/MQTT tokens and passwords, so those
# never get a raw tail, only the fixed description below.
TAIL_ALLOWED_STAGES = frozenset({'tar', 'offhost_copy', 'cleanup', 'mqtt_copy'})

STAGE_DESCRIPTIONS = {
    'preflight': 'Capacity or free-space check failed',
    'influx_backup': 'Influx online export or isolated restore/verification failed',
    'encrypt': 'Checkpoint encryption or restic verification failed',
    'tar': 'Archive assembly failed',
    'offhost_copy': 'Archive hashing or independent off-host copy failed',
    'cleanup': 'Decrypted staging cleanup failed',
    'mqtt_export': 'MQTT export, isolated restore or result validation failed',
    'mqtt_copy': 'MQTT archive hashing or independent off-host copy failed',
}

LOCK_NAME = 'daily-recovery.lock'
# Purely informational now. It used to feed a takeover decision (steal the
# lock if a file was older than this), which could -- and did -- steal a
# live owner's lock. It no longer influences acquisition at all: it is only
# ever surfaced as a note when refusing a conflicting acquire, if the file
# happens to look like it has been held unusually long.
LOCK_STALE_SECONDS = 30 * 60  # longer than the Task Scheduler execution time limit (20 min)

# Byte 0 of the lock file is a reserved marker: it is the only byte the OS
# lock actually covers. Informational metadata (pid/started_at/hostname) is
# always written starting at offset 1 and never touches byte 0, so reading or
# mutating that metadata (including in tests) never collides with the lock
# itself -- notably on Windows, where byte-range locks are mandatory even for
# unrelated processes' I/O to that exact byte.
_LOCK_MARKER_BYTES = 1

# Conservative redaction, kept as defense in depth for whichever stages are
# allowed to carry a stderr tail: anything that looks like it follows a
# credential keyword, plus any long base64/hex-shaped run.
_KEYWORD_VALUE = re.compile(
    r'(?i)\b(token|password|authorization)\b\s*[:=]?\s*(?:Bearer\s+)?(\S+)')
_LONG_SECRET_LIKE = re.compile(r'[A-Za-z0-9+/_=-]{32,}')

# mqtt-recovery.py generates its own timestamp independent of this script's
# `stamp`, so the archive path it reports cannot be checked against an exact
# expected path -- only that it is a direct child of DEST named like a
# well-formed mqtt-<UTC stamp> run directory, with the documented filename.
_MQTT_DIR_RE = re.compile(r'^mqtt-\d{8}T\d{6}Z$')


def redact(text):
    text = _KEYWORD_VALUE.sub(lambda m: m.group(1) + '=[redacted]', text)
    text = _LONG_SECRET_LIKE.sub('[redacted]', text)
    return text


def stderr_tail(data, lines=20):
    text = data.decode('utf-8', 'replace') if isinstance(data, (bytes, bytearray)) else str(data)
    return '\n'.join(text.splitlines()[-lines:])


class StageFailure(Exception):
    """A named pipeline stage failed; carries only sanitized evidence."""
    def __init__(self, stage, exit_code, tail):
        self.stage = stage
        self.exit_code = exit_code
        self.tail = redact(tail if isinstance(tail, str) else stderr_tail(tail))
        super().__init__('Stage %r failed (exit %s)' % (stage, exit_code))


class LockHeld(Exception):
    """Another (live) run already holds the exclusive OS lock."""
    def __init__(self, info):
        self.info = info
        super().__init__('Another recovery run appears to be in progress')


def cmd(args, timeout=600, stage=None):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as exc:
        tail = stderr_tail(exc.stderr or b'')
        if stage is None:
            raise RuntimeError('Recovery stage timed out; private output withheld')
        raise StageFailure(stage, 'timeout', tail)
    if p.returncode:
        if stage is None:
            raise RuntimeError('Recovery stage failed; private output withheld')
        raise StageFailure(stage, p.returncode, stderr_tail(p.stderr))
    return p.stdout.decode()


def new_status():
    return {name: {'status': 'pending'} for name in STAGES}


def mark_ok(status, name):
    status[name] = {'status': 'ok'}


def mark_failed(status, name, exit_code, tail=None, description=None):
    entry = dict(status='failed', exit_code=exit_code,
                 description=description or STAGE_DESCRIPTIONS.get(name, 'Stage failed'))
    if name in TAIL_ALLOWED_STAGES and tail:
        entry['stderr_tail'] = tail
    status[name] = entry


def record_failure(status, name, exc):
    """Record `exc` against stage `name` in `status`; returns the stage that
    actually failed (an exception raised by cmd() already names its own
    stage, which should always equal `name` here, but a stage that fails
    without going through cmd(), e.g. the tar step, does not)."""
    if isinstance(exc, StageFailure):
        mark_failed(status, exc.stage, exc.exit_code, tail=exc.tail)
        return exc.stage
    mark_failed(status, name, None, tail=redact(str(exc)))
    return name


def atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2) + '\n').encode()
    tmp = path.with_name(path.name + '.tmp-%d' % os.getpid())
    with open(tmp, 'wb') as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def write_status(status, overall, failing_stage=None):
    report = dict(observed_at=datetime.now(timezone.utc).isoformat(), overall=overall, stages=status)
    if failing_stage:
        report['failing_stage'] = failing_stage
    atomic_write_json(DEST / 'status.json', report)
    return report


def remove_staging(source, stamp):
    """Off-host Influx copy is verified by this point, so this run's decrypted
    staging directory is redundant; removed independently of the MQTT stage."""
    resolved = source.resolve()
    if resolved.parent != (ROOT / 'data').resolve() or resolved.name != 'daily-' + stamp:
        raise ValueError('Unexpected cleanup destination')
    shutil.rmtree(resolved)


def validate_mqtt_archive_path(archive_field):
    """Validate the `archive` field of mqtt-recovery.py's JSON result without
    knowing its independently-generated stamp: it must be a direct child of
    DEST, inside a well-formed mqtt-<stamp> directory, named as documented."""
    if not isinstance(archive_field, str) or not archive_field:
        raise ValueError('missing or empty archive path')
    resolved = Path(archive_field).resolve(strict=False)
    dest_resolved = DEST.resolve()
    if resolved.parent.parent != dest_resolved or not _MQTT_DIR_RE.match(resolved.parent.name):
        raise ValueError('archive path outside expected directory')
    if resolved.name != 'encrypted.tar':
        raise ValueError('unexpected archive filename')
    return resolved


class LockHandle:
    """This process's own handle on the OS-held recovery lock.

    `release_lock()` only ever unlocks and closes *this* file descriptor; it
    never unlinks the lock file by pathname, so it cannot affect a lock a
    different process has since acquired on the same path.
    """
    __slots__ = ('path', 'fd', 'released')

    def __init__(self, path, fd):
        self.path = path
        self.fd = fd
        self.released = False


def _lock_fd(fd):
    """Try to take the exclusive OS lock on the reserved marker byte of `fd`.

    Returns True if acquired, False if another live process already holds
    it. This is the *only* thing that decides acquisition -- no age or
    metadata check of any kind."""
    os.lseek(fd, 0, os.SEEK_SET)
    if sys.platform == 'win32':
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, _LOCK_MARKER_BYTES)
        except OSError:
            return False
        return True
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock_fd(fd):
    """Best-effort release of this fd's own OS lock; never raises."""
    try:
        if sys.platform == 'win32':
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, _LOCK_MARKER_BYTES)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def _read_lock_info(lock_path):
    """Best-effort read of the informational metadata stored after the
    reserved marker byte, plus the lock file's age. This is never used to
    decide takeover: missing, empty or corrupt metadata simply reads back as
    `{}`, and the caller must not treat that as license to steal the lock."""
    try:
        raw = lock_path.read_bytes()
        payload = json.loads(raw[_LOCK_MARKER_BYTES:]) if len(raw) > _LOCK_MARKER_BYTES else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}
    try:
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        age = None
    return payload, age


def acquire_lock(dest):
    """Acquire the exclusive recovery lock under `dest`.

    Acquisition succeeds if and only if this process obtains the OS-level
    lock on the lock file's reserved marker byte (`msvcrt.locking` on
    Windows, `fcntl.flock` elsewhere) -- see the module docstring for the
    full rationale. The file's age and any pid/started_at/hostname metadata
    inside it are informational only and never influence this decision: a
    live owner is never stolen from just because time passed, and unreadable
    or partial metadata seen during another process's own initialization
    never grants takeover. The lock file is never deleted on this path.

    On abnormal exit (crash, kill, power loss) the OS drops the lock when the
    process's descriptor is torn down; the next acquire then simply
    succeeds -- no manual unlink required or performed.
    """
    dest.mkdir(parents=True, exist_ok=True)
    lock_path = dest / LOCK_NAME
    flags = os.O_CREAT | os.O_RDWR
    if sys.platform == 'win32':
        flags |= os.O_BINARY
    fd = os.open(str(lock_path), flags, 0o644)
    if os.fstat(fd).st_size < _LOCK_MARKER_BYTES:
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, b'\0' * _LOCK_MARKER_BYTES)

    if not _lock_fd(fd):
        info, age = _read_lock_info(lock_path)
        os.close(fd)
        if age is not None:
            info = dict(info, observed_age_seconds=round(age, 1))
            if age > LOCK_STALE_SECONDS:
                info['note'] = ('lock file looks older than the %ds informational '
                                 'threshold; still treated as a live owner, not stolen'
                                 % LOCK_STALE_SECONDS)
        raise LockHeld(info)

    # OS lock is held from here on. Metadata below is informational only --
    # written strictly after the reserved marker byte, and its failure must
    # never affect the lock already held.
    try:
        payload = json.dumps(dict(pid=os.getpid(),
                                   started_at=datetime.now(timezone.utc).isoformat(),
                                   hostname=platform.node())).encode()
        os.lseek(fd, _LOCK_MARKER_BYTES, os.SEEK_SET)
        os.write(fd, payload)
        os.ftruncate(fd, _LOCK_MARKER_BYTES + len(payload))
        os.fsync(fd)
    except OSError:
        pass
    return LockHandle(lock_path, fd)


def release_lock(lock_handle):
    """Release this process's own OS lock and close its descriptor.

    Never unlinks the lock file by pathname -- doing so could remove or
    invalidate a lock a *different* process has since acquired on the same
    path, since this process's fd/lock is entirely independent of whatever
    the pathname currently points to. The file itself is left in place. A
    second release on the same handle, or a release of a handle from a
    failed acquire, is a no-op.
    """
    if lock_handle is None or lock_handle.released:
        return
    lock_handle.released = True
    _unlock_fd(lock_handle.fd)
    try:
        os.close(lock_handle.fd)
    except OSError:
        pass


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    lock_handle = acquire_lock(DEST)
    try:
        status = new_status()
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        source = ROOT / 'data' / ('daily-' + stamp)
        dest = DEST / stamp

        try:
            total = sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file())
            if total > 20 * 1024**3:
                raise StageFailure('preflight', None, 'PC backup capacity budget reached; no automatic deletion')
            if shutil.disk_usage(DEST).free < 20 * 1024**3:
                raise StageFailure('preflight', None, 'PC free-space reserve reached')
            mark_ok(status, 'preflight')
        except Exception as exc:
            failing = record_failure(status, 'preflight', exc)
            write_status(status, 'failed', failing)
            sys.exit(1)

        try:
            cmd([sys.executable, str(ROOT / 'scripts/influx-recovery.py'), '--out', str(source)],
                stage='influx_backup')
            mark_ok(status, 'influx_backup')
        except Exception as exc:
            failing = record_failure(status, 'influx_backup', exc)
            write_status(status, 'failed', failing)
            sys.exit(1)

        try:
            cmd([sys.executable, str(ROOT / 'scripts/encrypt-checkpoint.py'),
                 '--source', str(source), '--destination', str(dest)], stage='encrypt')
            mark_ok(status, 'encrypt')
        except Exception as exc:
            failing = record_failure(status, 'encrypt', exc)
            write_status(status, 'failed', failing)
            sys.exit(1)

        archive = dest / 'encrypted.tar'
        try:
            with tarfile.open(archive, 'w') as stream:
                stream.add(dest / 'repository', arcname='repository')
                stream.add(dest / 'encryption-verification.json', arcname='encryption-verification.json')
            mark_ok(status, 'tar')
        except Exception as exc:
            failing = record_failure(status, 'tar', exc)
            write_status(status, 'failed', failing)
            sys.exit(1)

        remote = '/home/david/iot-checkpoints/' + stamp + '.tar'
        influx_fields = None
        try:
            with archive.open('rb') as stream:
                checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
            cmd(['ssh', *SSH, HOST, 'umask 077; mkdir -p /home/david/iot-checkpoints; '
                 'test "$(du -sb /home/david/iot-checkpoints | cut -f1)" -lt 10737418240 && '
                 'test "$(df -B1 --output=avail /home/david/iot-checkpoints | tail -1)" -gt 21474836480'],
                stage='offhost_copy')
            cmd(['scp', *SSH, str(archive), HOST + ':' + remote + '.part'], stage='offhost_copy')
            observed = cmd(['ssh', *SSH, HOST, 'sha256sum ' + remote + '.part'], stage='offhost_copy').split()[0]
            if observed != checksum:
                raise StageFailure('offhost_copy', None, 'Independent copy checksum mismatch')
            cmd(['ssh', *SSH, HOST, 'test ! -e ' + remote + ' && mv ' + remote + '.part ' + remote],
                stage='offhost_copy')
            # Checksum verified: persist the Influx checkpoint now, before
            # staging cleanup or any MQTT work.
            influx_fields = dict(archive=str(archive), independent_copy=remote, sha256=checksum,
                                  native_restore_verified=True, encrypted_restore_verified=True,
                                  automatic_promotion=False)
            influx_report = dict(verified_at=datetime.now(timezone.utc).isoformat(), **influx_fields)
            atomic_write_json(DEST / 'latest-influx.json', influx_report)
            mark_ok(status, 'offhost_copy')
        except Exception as exc:
            failing = record_failure(status, 'offhost_copy', exc)
            write_status(status, 'failed', failing)
            sys.exit(1)

        # Cleanup is independent of the MQTT stages below: its failure must
        # not erase the Influx evidence just persisted, and must not block
        # the MQTT attempt.
        cleanup_failing_stage = None
        try:
            remove_staging(source, stamp)
            mark_ok(status, 'cleanup')
        except Exception as exc:
            cleanup_failing_stage = record_failure(status, 'cleanup', exc)
            write_status(status, 'partial', cleanup_failing_stage)

        mqtt_archive = None
        try:
            mqtt_stdout = cmd([sys.executable, str(ROOT / 'scripts/mqtt-recovery.py')], stage='mqtt_export')
            try:
                payload = json.loads(mqtt_stdout)
            except ValueError:
                raise StageFailure('mqtt_export', None, 'Malformed MQTT export response: invalid JSON')
            archive_field = payload.get('archive') if isinstance(payload, dict) else None
            try:
                mqtt_archive = validate_mqtt_archive_path(archive_field)
            except ValueError as verr:
                raise StageFailure('mqtt_export', None, 'Malformed MQTT export response: ' + str(verr))
            try:
                with mqtt_archive.open('rb') as fh:
                    fh.read(1)
            except OSError as oerr:
                raise StageFailure('mqtt_export', None, 'MQTT archive unreadable: ' + type(oerr).__name__)
            mark_ok(status, 'mqtt_export')
        except Exception as exc:
            failing = record_failure(status, 'mqtt_export', exc)
            write_status(status, 'partial', failing)
            sys.exit(1)

        mqtt_remote = '/home/david/iot-checkpoints/mqtt-' + stamp + '.tar'
        try:
            with mqtt_archive.open('rb') as stream:
                mqtt_checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
            cmd(['scp', *SSH, str(mqtt_archive), HOST + ':' + mqtt_remote + '.part'], stage='mqtt_copy')
            if cmd(['ssh', *SSH, HOST, 'sha256sum ' + mqtt_remote + '.part'],
                   stage='mqtt_copy').split()[0] != mqtt_checksum:
                raise StageFailure('mqtt_copy', None, 'Independent MQTT copy checksum mismatch')
            cmd(['ssh', *SSH, HOST, 'test ! -e ' + mqtt_remote + ' && mv ' + mqtt_remote + '.part ' + mqtt_remote],
                stage='mqtt_copy')
            mark_ok(status, 'mqtt_copy')
        except Exception as exc:
            failing = record_failure(status, 'mqtt_copy', exc)
            write_status(status, 'partial', failing)
            sys.exit(1)

        if cleanup_failing_stage:
            # Every other stage (including both MQTT stages) succeeded, but
            # cleanup did not: truthfully this is not a full success, so
            # latest.json (the full-success marker) is not written, even
            # though latest-influx.json and the MQTT copy are both current.
            write_status(status, 'partial', cleanup_failing_stage)
            report = dict(observed_at=datetime.now(timezone.utc).isoformat(), overall='partial',
                          failing_stage=cleanup_failing_stage, stages=status)
            print(json.dumps(report))
            sys.exit(1)

        report = dict(completed_at=datetime.now(timezone.utc).isoformat(), overall='success', stages=status,
                      **influx_fields, mqtt_independent_copy=mqtt_remote, mqtt_sha256=mqtt_checksum,
                      mqtt_restore_verified=True)
        atomic_write_json(DEST / 'latest.json', report)
        write_status(status, 'success')
        print(json.dumps(report))
    finally:
        release_lock(lock_handle)


def cli_main():
    """Entry point used when run as a script. Anything main() did not already
    turn into a controlled sys.exit (a lock conflict, or a genuinely
    unexpected exception -- including a report-write failure itself) is
    caught here and turned into a sanitized summary and non-zero exit; no raw
    traceback is ever printed."""
    try:
        main()
    except SystemExit:
        raise
    except LockHeld as exc:
        summary = dict(observed_at=datetime.now(timezone.utc).isoformat(), overall='skipped',
                       reason='lock_held', lock=exc.info)
        try:
            atomic_write_json(DEST / 'lock-conflict.json', summary)
        except Exception:
            pass
        print(json.dumps(summary))
        sys.exit(1)
    except Exception as exc:
        summary = dict(observed_at=datetime.now(timezone.utc).isoformat(), overall='error',
                       error=redact('%s: %s' % (type(exc).__name__, str(exc)))[:1000])
        try:
            atomic_write_json(DEST / 'status.json', summary)
        except Exception:
            pass
        print(json.dumps(summary))
        sys.exit(1)


if __name__ == '__main__': cli_main()
