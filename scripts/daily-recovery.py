"""Daily online export, isolated restore, encryption and independent host copy.

No live restart, endpoint change, retention deletion or standby refresh/promotion.
Requires the owner's existing Docker Desktop, SSH access and protected key.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
DEST = Path('D:/Backups/iot-backend')
SSH = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'HostKeyAlias=192.168.1.105']
HOST = 'david@192.168.1.106'


def cmd(args, timeout=600):
    p = subprocess.run(args, capture_output=True, timeout=timeout)
    if p.returncode: raise RuntimeError('Recovery stage failed; private output withheld')
    return p.stdout.decode()


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    if sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file()) > 20 * 1024**3:
        raise OSError('PC backup capacity budget reached; no automatic deletion')
    if shutil.disk_usage(DEST).free < 20 * 1024**3:
        raise OSError('PC free-space reserve reached')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    source = ROOT / 'data' / ('daily-' + stamp)
    dest = DEST / stamp
    cmd([sys.executable, str(ROOT / 'scripts/influx-recovery.py'), '--out', str(source)])
    cmd([sys.executable, str(ROOT / 'scripts/encrypt-checkpoint.py'), '--source', str(source), '--destination', str(dest)])
    archive = dest / 'encrypted.tar'
    with tarfile.open(archive, 'w') as stream:
        stream.add(dest / 'repository', arcname='repository')
        stream.add(dest / 'encryption-verification.json', arcname='encryption-verification.json')
    with archive.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    remote = '/home/david/iot-checkpoints/' + stamp + '.tar'
    cmd(['ssh', *SSH, HOST, 'umask 077; mkdir -p /home/david/iot-checkpoints; '
         'test "$(du -sb /home/david/iot-checkpoints | cut -f1)" -lt 10737418240 && '
         'test "$(df -B1 --output=avail /home/david/iot-checkpoints | tail -1)" -gt 21474836480'])
    cmd(['scp', *SSH, str(archive), HOST + ':' + remote + '.part'])
    observed = cmd(['ssh', *SSH, HOST, 'sha256sum ' + remote + '.part']).split()[0]
    if observed != checksum: raise RuntimeError('Independent copy checksum mismatch')
    cmd(['ssh', *SSH, HOST, 'test ! -e ' + remote + ' && mv ' + remote + '.part ' + remote])
    mqtt = json.loads(cmd([sys.executable, str(ROOT / 'scripts/mqtt-recovery.py')]))
    mqtt_archive = Path(mqtt['archive'])
    with mqtt_archive.open('rb') as stream:
        mqtt_checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    mqtt_remote = '/home/david/iot-checkpoints/mqtt-' + stamp + '.tar'
    cmd(['scp', *SSH, str(mqtt_archive), HOST + ':' + mqtt_remote + '.part'])
    if cmd(['ssh', *SSH, HOST, 'sha256sum ' + mqtt_remote + '.part']).split()[0] != mqtt_checksum:
        raise RuntimeError('Independent MQTT copy checksum mismatch')
    cmd(['ssh', *SSH, HOST, 'test ! -e ' + mqtt_remote + ' && mv ' + mqtt_remote + '.part ' + mqtt_remote])
    report = dict(completed_at=datetime.now(timezone.utc).isoformat(), archive=str(archive),
                  independent_copy=remote, sha256=checksum, native_restore_verified=True,
                  encrypted_restore_verified=True, automatic_promotion=False,
                  mqtt_independent_copy=mqtt_remote, mqtt_sha256=mqtt_checksum,
                  mqtt_restore_verified=True)
    (DEST / 'latest.json').write_bytes((json.dumps(report, indent=2)+'\n').encode())
    # Remove only this run's decrypted staging after both verified copies exist.
    resolved = source.resolve()
    if resolved.parent != (ROOT / 'data').resolve() or resolved.name != 'daily-' + stamp:
        raise ValueError('Unexpected cleanup destination')
    shutil.rmtree(resolved)
    print(json.dumps(report))


if __name__ == '__main__': main()
