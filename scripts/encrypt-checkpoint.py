"""Encrypt a verified Influx checkpoint and verify every restored file in Docker.

The disposable container has no network or host mounts. Nothing is published.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import secrets

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).with_name('influx-recovery.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

# (path under the repository root, label inside /checkpoint/credentials, required)
# secrets/influx-restic-password must never be listed: it is the key for this repository.
CREDENTIALS = [('.env', 'iot.env', True),
               ('mosquitto/password.txt', 'mosquitto-password.txt', True),
               ('secrets/influx-operator-token', 'influx-operator-token', True),
               ('secrets/threadripper-infra-token.json', 'threadripper-infra-token.json', False),
               ('secrets/grafana-infra-token.json', 'grafana-infra-token.json', False)]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    args = p.parse_args()
    assert (args.source / 'verification.json').is_file(), 'Verify native database restore first'
    assert not args.destination.exists(), 'Destination must be new'
    r.private_directory(args.destination)
    r.private_directory(r.ROOT / 'secrets')
    key = r.ROOT / 'secrets/influx-restic-password'
    if not key.exists(): key.write_bytes(secrets.token_urlsafe(48).encode())
    name = 'iot-encrypt-' + secrets.token_hex(4)
    created = False
    try:
        r.command(['docker', 'run', '-d', '--name', name, '--network', 'none', '--memory', '1g',
                   '--cpus', '2', '--entrypoint', 'sleep', 'threadripper-validation', '1800'])
        created = True
        r.command(['docker', 'cp', str(args.source), name + ':/checkpoint'])
        r.command(['docker', 'cp', str(key), name + ':/password'])
        r.command(['docker', 'exec', name, 'mkdir', '/checkpoint/credentials'])
        included, skipped = [], []
        for relative, label, required in CREDENTIALS:
            file = r.ROOT / relative
            if not file.is_file():
                if required: raise FileNotFoundError('Required credential file missing: ' + label)
                skipped.append(label)
                continue
            r.command(['docker', 'cp', str(file), name + ':/checkpoint/credentials/' + label])
            included.append(label)
        r.command(['docker', 'exec', name, 'sh', '-c',
            'export RESTIC_REPOSITORY=/repository RESTIC_PASSWORD_FILE=/password; '
            'restic init && restic backup /checkpoint && restic check --read-data && '
            'restic restore latest --target /restore --verify && diff -r /checkpoint /restore/checkpoint'])
        snapshots = json.loads(r.command(['docker', 'exec', name, 'restic', '-r', '/repository',
                                  '--password-file', '/password', 'snapshots', '--json']))
        r.command(['docker', 'cp', name + ':/repository', str(args.destination / 'repository')])
        verification = dict(snapshot=snapshots[-1]['id'], all_data_checked=True,
                            restored_files_identical=True, database_drill='source/verification.json',
                            credentials_included=included, credentials_skipped=skipped)
        (args.destination / 'encryption-verification.json').write_bytes((json.dumps(verification, indent=2)+'\n').encode())
        print(json.dumps(verification))
    finally:
        if created: r.command(['docker', 'rm', '-f', '-v', name])


if __name__ == '__main__': main()
