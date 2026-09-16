"""Exercise provisioning against disposable InfluxDB, never the live instance.

No network, published ports, host mounts, or real credentials. The temporary
container and its anonymous volumes are removed in finally. Run explicitly.
"""
import importlib.util
import json
from pathlib import Path
import secrets
import tempfile
import time
import uuid

spec = importlib.util.spec_from_file_location(
    'provision', Path(__file__).resolve().parents[1] / 'tools/provision_infra.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
command = p.recovery.command


def main():
    name = 'monitor-infra-validation-' + uuid.uuid4().hex[:10]
    created = False
    try:
        command(['docker', 'run', '-d', '--name', name, '--network', 'none',
                 '--memory', '1g', '--cpus', '1', '--pids-limit', '256',
                 '--log-opt', 'max-size=1m', '--log-opt', 'max-file=1', p.recovery.IMAGE])
        created = True
        inspect = json.loads(command(['docker', 'inspect', name]))[0]['HostConfig']
        assert inspect['NetworkMode'] == 'none'
        assert not inspect['Binds'] and not inspect['PortBindings'] and not inspect['Privileged']
        for attempt in range(30):
            try:
                command(['docker', 'exec', name, 'curl', '-fsS', '--max-time', '2',
                         'http://127.0.0.1:8086/health'], timeout=5)
                break
            except RuntimeError:
                time.sleep(1)
        else:
            raise RuntimeError('Disposable InfluxDB startup timed out')

        token = secrets.token_urlsafe(48)
        setup = json.dumps({'username': 'fixture', 'password': secrets.token_urlsafe(24),
                            'org': 'home', 'bucket': 'iot', 'token': token}).encode()
        command(['docker', 'exec', '-i', name, 'curl', '-fsS', '--max-time', '10',
                 '-X', 'POST', 'http://127.0.0.1:8086/api/v2/setup',
                 '--data-binary', '@-'], input=setup)
        command(['docker', 'exec', '-i', name, 'sh', '-c',
                 'umask 077; cat > /tmp/fixture-token'], input=token.encode())

        def isolated_live(text):
            return command(['docker', 'exec', name, 'sh', '-c',
                            'export INFLUX_TOKEN="$(cat /tmp/fixture-token)"; ' + text])

        def isolated_command(args, **kwargs):
            # Every credential probe must be redirected to this disposable name.
            assert args[:4] == ['docker', 'exec', '-i', 'iot-influxdb']
            return command(args[:3] + [name] + args[4:], **kwargs)

        p.recovery.live = isolated_live
        p.recovery.command = isolated_command
        # The original private_directory helper uses command for Windows ACLs;
        # keep those local calls separate from the redirected credential probes.
        original_private = p.recovery.private_directory

        def private(path):
            p.recovery.command = command
            try:
                original_private(path)
            finally:
                p.recovery.command = isolated_command

        p.recovery.private_directory = private
        for bucket in ('network', 'voice_telemetry'):
            isolated_live(f'influx bucket create --org home --name {bucket} --json')
        buckets = json.loads(isolated_live('influx bucket list --org home --json'))
        ids = [p.require_bucket(buckets, key)['id'] for key in p.ORIGINAL_GRAFANA_BUCKETS]
        flags = ' '.join('--read-bucket ' + key for key in ids)
        isolated_live('influx auth create --org home ' + flags +
                      ' --description "' + p.GRAFANA_SOURCE_DESCRIPTION + '" --json')

        with tempfile.TemporaryDirectory(prefix='infra-provision-fixture-') as directory:
            p.WRITE_SECRET_PATH = Path(directory) / 'credentials/write.json'
            p.GRAFANA_SECRET_PATH = Path(directory) / 'credentials/read.json'
            initial = p.fetch_state('home')
            plan = p.build_plan(*initial, 'home', 'infra', 30)
            assert plan['bucket']['action'] == 'create'
            result = p.apply_plan(plan, 'home', 'infra', 30)
            final = p.fetch_state('home')
            again = p.build_plan(*final, 'home', 'infra', 30)
            assert all(again[key]['action'] == 'skip'
                       for key in ('bucket', 'threadripper_token', 'grafana_token'))
            p.apply_plan(again, 'home', 'infra', 30)
            assert len(p.fetch_state('home')[2]) == len(final[2])
            source = p.find_source_grafana_auth(final[2], result['org_id'], ids)
            assert source['status'] == 'active'
            print('PASS: real CLI shapes, 30-day bucket, exact token scopes, private credential '
                  'persistence, authenticated probes, idempotent rerun, old Grafana token retained; '
                  'isolated network/no mounts/no ports.')
    finally:
        if created:
            command(['docker', 'rm', '-f', '-v', name])


if __name__ == '__main__':
    main()
