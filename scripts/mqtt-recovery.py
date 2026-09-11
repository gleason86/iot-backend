"""Flush/copy live broker persistence without disconnecting clients; restore in isolation."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import secrets
import tarfile
import time

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).with_name('influx-recovery.py'))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
IMAGE = 'eclipse-mosquitto@sha256:077fe4ff4c49df1e860c98335c77dda08360629e0e2a718147027e4db3eace9d'


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = Path('D:/Backups/iot-backend') / ('mqtt-' + stamp)
    r.private_directory(out)
    name = 'mqtt-restore-' + secrets.token_hex(4)
    helper = name + '-encrypt'
    made = []
    started = time.monotonic()
    try:
        r.command(['docker', 'kill', '--signal', 'SIGUSR1', 'iot-mosquitto'])
        time.sleep(1)
        first = r.command(['docker', 'exec', 'iot-mosquitto', 'sha256sum', '/mosquitto/data/mosquitto.db']).split()[0]
        r.command(['docker', 'cp', 'iot-mosquitto:/mosquitto/data/mosquitto.db', str(out / 'mosquitto.db')])
        second = r.command(['docker', 'exec', 'iot-mosquitto', 'sha256sum', '/mosquitto/data/mosquitto.db']).split()[0]
        import hashlib
        assert first == second == hashlib.sha256((out / 'mosquitto.db').read_bytes()).hexdigest().encode()
        env = {}
        for line in (r.ROOT / '.env').read_bytes().decode().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                if key in ('MQTT_USER', 'MQTT_PASSWORD'): env[key] = value.strip().strip('"').strip("'")
        assert all(env.get(k) for k in ('MQTT_USER', 'MQTT_PASSWORD'))
        r.command(['docker', 'run', '-d', '--name', name, '--network', 'none', '--memory', '128m',
                   '--user', 'root', '--entrypoint', 'sh', IMAGE, '-c',
                   'while test ! -f /tmp/start; do sleep 1; done; chown -R mosquitto:mosquitto /mosquitto/data; exec mosquitto -c /mosquitto/config/mosquitto.conf'])
        made.append(name)
        r.command(['docker', 'cp', str(out / 'mosquitto.db'), name + ':/mosquitto/data/mosquitto.db'])
        r.command(['docker', 'cp', str(r.ROOT / 'mosquitto/password.txt'), name + ':/mosquitto/config/password.txt'])
        conf = b'listener 1883 127.0.0.1\nallow_anonymous false\npassword_file /mosquitto/config/password.txt\npersistence true\npersistence_location /mosquitto/data/\nlog_dest stdout\n'
        r.command(['docker', 'exec', '-i', name, 'sh', '-c', 'cat > /mosquitto/config/mosquitto.conf'], conf)
        for field, path in [('MQTT_USER', '/tmp/user'), ('MQTT_PASSWORD', '/tmp/password')]:
            r.command(['docker', 'exec', '-i', name, 'sh', '-c', 'umask 077; cat > ' + path], env[field].encode())
        r.command(['docker', 'exec', name, 'touch', '/tmp/start']); time.sleep(1)
        prefix = 'u="$(cat /tmp/user)"; p="$(cat /tmp/password)"; '
        r.command(['docker', 'exec', name, 'sh', '-c', prefix +
                   'mosquitto_pub -h 127.0.0.1 -u "$u" -P "$p" -q 1 -r -t recovery/drill -m verified-checkpoint'])
        r.command(['docker', 'kill', '--signal', 'SIGUSR1', name]); time.sleep(1)
        r.command(['docker', 'restart', name]); time.sleep(1)
        message = r.command(['docker', 'exec', name, 'sh', '-c', prefix +
                   'mosquitto_sub -h 127.0.0.1 -u "$u" -P "$p" -q 1 -t recovery/drill -C 1 -W 5'])
        assert message.strip() == b'verified-checkpoint'
        r.command(['docker', 'run', '-d', '--name', helper, '--network', 'none', '--memory', '512m',
                   '--entrypoint', 'sleep', 'threadripper-validation', '600'])
        made.append(helper)
        r.command(['docker', 'exec', helper, 'mkdir', '/checkpoint'])
        for source, label in [(out / 'mosquitto.db', 'mosquitto.db'),
                              (r.ROOT / 'mosquitto/password.txt', 'password.txt'),
                              (r.ROOT / 'mosquitto/mosquitto.conf', 'mosquitto.conf')]:
            r.command(['docker', 'cp', str(source), helper + ':/checkpoint/' + label])
        r.command(['docker', 'exec', '-i', helper, 'sh', '-c', 'umask 077; cat > /checkpoint/client-credentials.json'], json.dumps(env).encode())
        r.command(['docker', 'cp', str(r.ROOT / 'secrets/influx-restic-password'), helper + ':/password'])
        r.command(['docker', 'exec', helper, 'sh', '-c',
            'export RESTIC_REPOSITORY=/repository RESTIC_PASSWORD_FILE=/password; restic init && '
            'restic backup /checkpoint && restic check --read-data && restic restore latest --target /restore --verify && diff -r /checkpoint /restore/checkpoint'])
        snapshot = json.loads(r.command(['docker', 'exec', helper, 'restic', '-r', '/repository', '--password-file', '/password', 'snapshots', '--json']))[-1]['id']
        r.command(['docker', 'cp', helper + ':/repository', str(out / 'repository')])
        report = dict(observed_at=datetime.now(timezone.utc).isoformat(), image=IMAGE,
                      elapsed_seconds=round(time.monotonic()-started,3), snapshot=snapshot,
                      live_checkpoint_hash=first.decode(), live_clients='not disconnected',
                      isolation='network none, no ports, no host binds or production volume',
                      original_credentials_verified=True, retained_fixture_survived_restart=True,
                      encrypted_restore_identical=True, production_replay='not performed')
        (out / 'verification.json').write_bytes((json.dumps(report, indent=2)+'\n').encode())
        with tarfile.open(out / 'encrypted.tar', 'w') as stream:
            stream.add(out / 'repository', arcname='repository')
            stream.add(out / 'verification.json', arcname='verification.json')
        (out / 'mosquitto.db').unlink()
        print(json.dumps(dict(report=report, archive=str(out / 'encrypted.tar')), indent=2))
    finally:
        for container in reversed(made): r.command(['docker', 'rm', '-f', '-v', container])


if __name__ == '__main__': main()
