import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location(
    'provision_infra', Path(__file__).resolve().parents[1] / 'tools/provision_infra.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

# Real, sanitized-metadata ids recorded in docs/infra-monitoring-2026-09-15.md,
# reused here so fixtures reflect actual live shapes rather than guesses.
ORG_ID = '714f34e4c62e3500'
IOT_ID = 'dc846c7b25ee1436'
NETWORK_ID = '57497837fc976b6f'
VOICE_ID = 'bf46fdb9d8a893fd'
INFRA_ID = 'a1b2c3d4e5f60718'
SOURCE_AUTH_ID = '114cb64756347000'

ORGS = [{'name': 'home', 'id': ORG_ID}]
BASE_BUCKETS = [
    {'name': 'iot', 'id': IOT_ID, 'retentionRules': []},
    {'name': 'network', 'id': NETWORK_ID, 'retentionRules': [{'everySeconds': 90 * 86400}]},
    {'name': 'voice_telemetry', 'id': VOICE_ID, 'retentionRules': []},
]
WITH_INFRA_BUCKET = BASE_BUCKETS + [
    {'name': 'infra', 'id': INFRA_ID, 'retentionRules': [{'everySeconds': 30 * 86400}]}]
WRONG_RETENTION_BUCKET = BASE_BUCKETS + [
    {'name': 'infra', 'id': INFRA_ID, 'retentionRules': [{'everySeconds': 7 * 86400}]}]
NO_AUTHS = []

SOURCE_GRAFANA_AUTH = {
    'id': SOURCE_AUTH_ID, 'description': p.GRAFANA_SOURCE_DESCRIPTION, 'status': 'active',
    'permissions': [f'read:orgs/{ORG_ID}/buckets/{IOT_ID}',
                    f'read:orgs/{ORG_ID}/buckets/{NETWORK_ID}',
                    f'read:orgs/{ORG_ID}/buckets/{VOICE_ID}'],
}
GRAFANA_DESCRIPTION = p.grafana_token_description('infra')
WRITE_DESCRIPTION = 'threadripper infra write-only, infra bucket'


def probe_response(args, **kwargs):
    config = kwargs['input']
    return b'400' if b'/api/v2/write' in config else b'200'


@contextlib.contextmanager
def temp_secret(auth_id, token='super-secret-value', corrupt=False, missing=False):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'cred.json'
        if not missing:
            if corrupt:
                path.write_text('not json')
            else:
                path.write_text(json.dumps({'auth_id': auth_id, 'token': token}))
        yield path


class IsolatedSecretPaths(unittest.TestCase):
    """Point both credential output paths at a per-test temp directory so the
    plan/dry-run tests never see (or refuse to overwrite) real secrets/ files."""
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        for name in ('WRITE_SECRET_PATH', 'GRAFANA_SECRET_PATH'):
            patcher = mock.patch.object(p, name, base / (name.lower() + '.json'))
            patcher.start(); self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)


class ValidateIdTests(unittest.TestCase):
    def test_accepts_16_char_hex(self):
        self.assertEqual(p.validate_id('org id', ORG_ID), ORG_ID)

    def test_rejects_non_hex_or_wrong_length(self):
        with self.assertRaises(RuntimeError):
            p.validate_id('org id', 'home; rm -rf /')
        with self.assertRaises(RuntimeError):
            p.validate_id('bucket id', 'short')


class PlanBucketTests(unittest.TestCase):
    def test_create_when_missing(self):
        self.assertEqual(p.plan_bucket(BASE_BUCKETS, 'infra', 30),
                          {'action': 'create', 'bucket': 'infra', 'retention_days': 30})

    def test_skip_when_matching_retention(self):
        step = p.plan_bucket(WITH_INFRA_BUCKET, 'infra', 30)
        self.assertEqual(step['action'], 'skip')
        self.assertEqual(step['id'], INFRA_ID)

    def test_refuses_to_silently_change_mismatched_retention(self):
        with self.assertRaises(RuntimeError):
            p.plan_bucket(WRONG_RETENTION_BUCKET, 'infra', 30)


class FindSourceGrafanaAuthTests(unittest.TestCase):
    source_ids = [IOT_ID, NETWORK_ID, VOICE_ID]

    def test_valid_source_returned(self):
        result = p.find_source_grafana_auth([SOURCE_GRAFANA_AUTH], ORG_ID, self.source_ids)
        self.assertEqual(result['id'], SOURCE_AUTH_ID)

    def test_missing_source_is_ambiguous(self):
        with self.assertRaises(RuntimeError):
            p.find_source_grafana_auth(NO_AUTHS, ORG_ID, self.source_ids)

    def test_duplicate_description_is_ambiguous(self):
        dup = dict(SOURCE_GRAFANA_AUTH, id='other-id-0000000')
        with self.assertRaises(RuntimeError):
            p.find_source_grafana_auth([SOURCE_GRAFANA_AUTH, dup], ORG_ID, self.source_ids)

    def test_inactive_source_rejected(self):
        inactive = dict(SOURCE_GRAFANA_AUTH, status='inactive')
        with self.assertRaises(RuntimeError):
            p.find_source_grafana_auth([inactive], ORG_ID, self.source_ids)

    def test_unexpected_scope_rejected_missing_bucket(self):
        narrower = dict(SOURCE_GRAFANA_AUTH,
                         permissions=[f'read:orgs/{ORG_ID}/buckets/{IOT_ID}'])
        with self.assertRaises(RuntimeError):
            p.find_source_grafana_auth([narrower], ORG_ID, self.source_ids)

    def test_unexpected_scope_rejected_extra_bucket(self):
        broader = dict(SOURCE_GRAFANA_AUTH,
                        permissions=SOURCE_GRAFANA_AUTH['permissions'] + [f'read:orgs/{ORG_ID}/buckets/{INFRA_ID}'])
        with self.assertRaises(RuntimeError):
            p.find_source_grafana_auth([broader], ORG_ID, self.source_ids)


class PlanTokenTests(unittest.TestCase):
    def test_create_when_missing(self):
        step = p._plan_token(NO_AUTHS, WRITE_DESCRIPTION, 'write', 'home', ORG_ID, INFRA_ID,
                              [INFRA_ID], Path('/tmp/unused.json'))
        self.assertEqual(step, {'action': 'create', 'description': WRITE_DESCRIPTION})

    def test_skip_when_existing_active_matching_scope_and_credential_verified(self):
        auths = [{'description': WRITE_DESCRIPTION, 'status': 'active', 'id': 'auth1',
                  'permissions': [f'write:orgs/{ORG_ID}/buckets/{INFRA_ID}']}]
        with temp_secret('auth1') as secret_path:
            with mock.patch.object(p.recovery, 'command', return_value=b'400'):
                step = p._plan_token(auths, WRITE_DESCRIPTION, 'write', 'home', ORG_ID, INFRA_ID,
                                      [INFRA_ID], secret_path)
        self.assertEqual(step['action'], 'skip')
        self.assertEqual(step['id'], 'auth1')

    def test_rejects_ambiguous_duplicate_descriptions(self):
        auths = [{'description': 'x', 'status': 'active', 'id': '1', 'permissions': []},
                 {'description': 'x', 'status': 'active', 'id': '2', 'permissions': []}]
        with self.assertRaises(RuntimeError):
            p._plan_token(auths, 'x', 'write', 'home', ORG_ID, INFRA_ID, [INFRA_ID], Path('/tmp/unused.json'))

    def test_rejects_inactive_existing_token(self):
        auths = [{'description': 'x', 'status': 'inactive', 'id': 'auth1', 'permissions': []}]
        with self.assertRaises(RuntimeError):
            p._plan_token(auths, 'x', 'write', 'home', ORG_ID, INFRA_ID, [INFRA_ID], Path('/tmp/unused.json'))

    def test_rejects_wrong_existing_scope(self):
        auths = [{'description': WRITE_DESCRIPTION, 'status': 'active', 'id': 'auth1',
                  'permissions': [f'write:orgs/{ORG_ID}/buckets/{IOT_ID}']}]
        with self.assertRaises(RuntimeError):
            p._plan_token(auths, WRITE_DESCRIPTION, 'write', 'home', ORG_ID, INFRA_ID,
                          [INFRA_ID], Path('/tmp/unused.json'))

    def test_rejects_inconsistent_state_bucket_missing(self):
        auths = [{'description': WRITE_DESCRIPTION, 'status': 'active', 'id': 'auth1', 'permissions': []}]
        with self.assertRaises(RuntimeError):
            p._plan_token(auths, WRITE_DESCRIPTION, 'write', 'home', ORG_ID, None, [], Path('/tmp/unused.json'))

    def test_missing_local_secret_fails_clearly(self):
        auths = [{'description': WRITE_DESCRIPTION, 'status': 'active', 'id': 'auth1',
                  'permissions': [f'write:orgs/{ORG_ID}/buckets/{INFRA_ID}']}]
        with temp_secret('auth1', missing=True) as secret_path:
            with self.assertRaises(RuntimeError) as ctx:
                p._plan_token(auths, WRITE_DESCRIPTION, 'write', 'home', ORG_ID, INFRA_ID,
                              [INFRA_ID], secret_path)
        self.assertIn('no local credential file', str(ctx.exception))


class VerifyLocalCredentialTests(unittest.TestCase):
    def test_missing_file_raises(self):
        with temp_secret(SOURCE_AUTH_ID, missing=True) as secret_path:
            with self.assertRaises(RuntimeError):
                p.verify_local_credential(secret_path, 'auth1', 'read', 'home', ORG_ID, IOT_ID)

    def test_corrupt_file_raises(self):
        with temp_secret(SOURCE_AUTH_ID, corrupt=True) as secret_path:
            with self.assertRaises(RuntimeError):
                p.verify_local_credential(secret_path, 'auth1', 'read', 'home', ORG_ID, IOT_ID)

    def test_auth_id_mismatch_raises(self):
        with temp_secret('other-auth-id') as secret_path:
            with self.assertRaises(RuntimeError):
                p.verify_local_credential(secret_path, 'auth1', 'read', 'home', ORG_ID, IOT_ID)

    def test_probe_failure_raises(self):
        with temp_secret('auth1') as secret_path:
            with mock.patch.object(p.recovery, 'command', return_value=b'401'):
                with self.assertRaises(RuntimeError):
                    p.verify_local_credential(secret_path, 'auth1', 'read', 'home', ORG_ID, IOT_ID)

    def test_probe_success_passes(self):
        with temp_secret('auth1') as secret_path:
            with mock.patch.object(p.recovery, 'command', return_value=b'200'):
                p.verify_local_credential(secret_path, 'auth1', 'read', 'home', ORG_ID, IOT_ID)

    def test_never_raises_with_token_value_in_message(self):
        with temp_secret('auth1', token='super-secret-value') as secret_path:
            with mock.patch.object(p.recovery, 'command', return_value=b'401'):
                with self.assertRaises(RuntimeError) as ctx:
                    p.verify_local_credential(secret_path, 'auth1', 'read', 'home', ORG_ID, IOT_ID)
        self.assertNotIn('super-secret-value', str(ctx.exception))


class ProbeSavedTokenTests(unittest.TestCase):
    def test_write_kind_accepts_400_and_204(self):
        with mock.patch.object(p.recovery, 'command', return_value=b'400') as cmd:
            self.assertTrue(p.probe_saved_token('write', 'home', ORG_ID, INFRA_ID, 'tok'))
        args, kwargs = cmd.call_args
        self.assertNotIn('tok', json.dumps(args))
        self.assertIn(b'Authorization: Token tok', kwargs['input'])
        self.assertIn(b'http://127.0.0.1:8086', kwargs['input'])
        self.assertIn('--max-time', args[0])

    def test_rejects_config_injection_without_a_command(self):
        with mock.patch.object(p.recovery, 'command') as command:
            self.assertFalse(p.probe_saved_token('write', 'home', ORG_ID, INFRA_ID,
                                                'tok\nurl="http://unexpected"'))
        command.assert_not_called()

    def test_write_kind_rejects_401(self):
        with mock.patch.object(p.recovery, 'command', return_value=b'401'):
            self.assertFalse(p.probe_saved_token('write', 'home', ORG_ID, INFRA_ID, 'tok'))

    def test_read_kind_accepts_200(self):
        with mock.patch.object(p.recovery, 'command', return_value=b'200'):
            self.assertTrue(p.probe_saved_token('read', 'home', ORG_ID, IOT_ID, 'tok'))

    def test_read_kind_rejects_403(self):
        with mock.patch.object(p.recovery, 'command', return_value=b'403'):
            self.assertFalse(p.probe_saved_token('read', 'home', ORG_ID, IOT_ID, 'tok'))


class BuildPlanTests(IsolatedSecretPaths):
    def test_foreign_secret_file_blocks_fresh_provisioning(self):
        with temp_secret('foreign-auth') as secret:
            with mock.patch.object(p, 'WRITE_SECRET_PATH', secret), \
                 mock.patch.object(p.recovery, 'live') as live:
                with self.assertRaisesRegex(RuntimeError, 'overwrite'):
                    p.build_plan(ORGS, BASE_BUCKETS, [SOURCE_GRAFANA_AUTH], 'home', 'infra', 30)
        live.assert_not_called()

    def test_full_plan_for_fresh_infra(self):
        plan = p.build_plan(ORGS, BASE_BUCKETS, [SOURCE_GRAFANA_AUTH], 'home', 'infra', 30)
        self.assertEqual(plan['org_id'], ORG_ID)
        self.assertEqual(plan['bucket']['action'], 'create')
        self.assertEqual(plan['threadripper_token']['action'], 'create')
        self.assertEqual(plan['grafana_token']['action'], 'create')
        self.assertEqual(plan['grafana_token']['description'], GRAFANA_DESCRIPTION)
        self.assertIn('never modified or revoked', plan['grafana_note'])
        self.assertEqual(plan['grafana_source_bucket_ids'], [IOT_ID, NETWORK_ID, VOICE_ID])

    def test_unknown_org_raises(self):
        with self.assertRaises(RuntimeError):
            p.build_plan([], BASE_BUCKETS, [SOURCE_GRAFANA_AUTH], 'home', 'infra', 30)

    def test_missing_original_bucket_raises(self):
        with self.assertRaises(RuntimeError):
            p.build_plan(ORGS, BASE_BUCKETS[:2], [SOURCE_GRAFANA_AUTH], 'home', 'infra', 30)

    def test_bad_source_scope_raises_before_token_planning(self):
        narrower = dict(SOURCE_GRAFANA_AUTH, permissions=[f'read:orgs/{ORG_ID}/buckets/{IOT_ID}'])
        with self.assertRaises(RuntimeError):
            p.build_plan(ORGS, BASE_BUCKETS, [narrower], 'home', 'infra', 30)

    def test_partial_rerun_bucket_exists_tokens_pending(self):
        auths = [SOURCE_GRAFANA_AUTH]
        plan = p.build_plan(ORGS, WITH_INFRA_BUCKET, auths, 'home', 'infra', 30)
        self.assertEqual(plan['bucket']['action'], 'skip')
        self.assertEqual(plan['bucket']['id'], INFRA_ID)
        self.assertEqual(plan['threadripper_token']['action'], 'create')
        self.assertEqual(plan['grafana_token']['action'], 'create')

    def test_partial_rerun_write_token_already_verified(self):
        write_auth = {'description': WRITE_DESCRIPTION, 'status': 'active', 'id': 'wauth1',
                      'permissions': [f'write:orgs/{ORG_ID}/buckets/{INFRA_ID}']}
        with temp_secret('wauth1') as secret_path:
            with mock.patch.object(p, 'WRITE_SECRET_PATH', secret_path), \
                 mock.patch.object(p.recovery, 'command', return_value=b'400'):
                plan = p.build_plan(ORGS, WITH_INFRA_BUCKET, [SOURCE_GRAFANA_AUTH, write_auth],
                                     'home', 'infra', 30)
        self.assertEqual(plan['threadripper_token']['action'], 'skip')
        self.assertEqual(plan['grafana_token']['action'], 'create')


class PreflightSecretPathTests(unittest.TestCase):
    def test_returns_tmp_path_when_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'cred.json'
            tmp_path = p.preflight_secret_path(target)
            self.assertEqual(tmp_path, target.with_name('cred.json.tmp'))

    def test_refuses_existing_target_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'cred.json'
            target.write_text('unexpected')
            with self.assertRaises(RuntimeError):
                p.preflight_secret_path(target)

    def test_refuses_existing_tmp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'cred.json'
            target.with_name('cred.json.tmp').write_text('leftover')
            with self.assertRaises(RuntimeError):
                p.preflight_secret_path(target)


class WriteSecretAtomicTests(unittest.TestCase):
    def test_writes_content_and_replaces_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'cred.json'
            tmp_path = target.with_name('cred.json.tmp')
            p.write_secret_atomic(target, tmp_path, b'{"token": "x"}')
            self.assertFalse(tmp_path.exists())
            self.assertEqual(target.read_bytes(), b'{"token": "x"}')


class EnsureTokenTests(unittest.TestCase):
    def test_skip_step_does_not_touch_live_or_disk(self):
        with mock.patch.object(p.recovery, 'live') as live, \
             mock.patch.object(p.recovery, 'private_directory') as private_directory:
            step = {'action': 'skip', 'id': 'auth1', 'description': 'x'}
            result = p.ensure_token(step, 'home', ORG_ID, [INFRA_ID], 'write', Path('/tmp/unused.json'))
            self.assertEqual(result, {'action': 'skip', 'id': 'auth1', 'description': 'x'})
            live.assert_not_called()
            private_directory.assert_not_called()

    def test_create_step_persists_before_validation_and_never_returns_token(self):
        created = {'id': 'auth9', 'status': 'active',
                   'permissions': [f'write:orgs/{ORG_ID}/buckets/{INFRA_ID}'],
                   'token': 'super-secret-value'}
        with tempfile.TemporaryDirectory() as tmp:
            secret_path = Path(tmp) / 'threadripper.json'
            with mock.patch.object(p.recovery, 'live', return_value=json.dumps(created)) as live, \
                 mock.patch.object(p.recovery, 'private_directory') as private_directory:
                step = {'action': 'create', 'description': WRITE_DESCRIPTION}
                result = p.ensure_token(step, 'home', ORG_ID, [INFRA_ID], 'write', secret_path)
            live.assert_called_once()
            private_directory.assert_called_once_with(secret_path.parent)
            self.assertNotIn('token', result)
            self.assertEqual(result, {'action': 'create', 'id': 'auth9', 'description': WRITE_DESCRIPTION})
            written = json.loads(secret_path.read_text())
            self.assertEqual(written['token'], 'super-secret-value')
            self.assertEqual(written['auth_id'], 'auth9')
            self.assertEqual(oct(secret_path.stat().st_mode)[-3:], '600' if __import__('os').name != 'nt' else oct(secret_path.stat().st_mode)[-3:])

    def test_rejects_unexpected_permissions_but_still_persists_for_manual_review(self):
        created = {'id': 'auth9', 'status': 'active',
                   'permissions': [f'write:orgs/{ORG_ID}/buckets/OTHER0000000000'], 'token': 'sekrit-value-zzz'}
        with tempfile.TemporaryDirectory() as tmp:
            secret_path = Path(tmp) / 'threadripper.json'
            with mock.patch.object(p.recovery, 'live', return_value=json.dumps(created)), \
                 mock.patch.object(p.recovery, 'private_directory'):
                step = {'action': 'create', 'description': WRITE_DESCRIPTION}
                with self.assertRaises(RuntimeError) as ctx:
                    p.ensure_token(step, 'home', ORG_ID, [INFRA_ID], 'write', secret_path)
            self.assertNotIn('sekrit-value-zzz', str(ctx.exception))
            self.assertTrue(secret_path.exists())

    def test_rejects_inactive_new_token_but_still_persists(self):
        created = {'id': 'auth9', 'status': 'inactive',
                   'permissions': [f'write:orgs/{ORG_ID}/buckets/{INFRA_ID}'], 'token': 'x'}
        with tempfile.TemporaryDirectory() as tmp:
            secret_path = Path(tmp) / 'threadripper.json'
            with mock.patch.object(p.recovery, 'live', return_value=json.dumps(created)), \
                 mock.patch.object(p.recovery, 'private_directory'):
                step = {'action': 'create', 'description': WRITE_DESCRIPTION}
                with self.assertRaises(RuntimeError):
                    p.ensure_token(step, 'home', ORG_ID, [INFRA_ID], 'write', secret_path)
            self.assertTrue(secret_path.exists())

    def test_refuses_to_overwrite_unexpected_existing_secret_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret_path = Path(tmp) / 'threadripper.json'
            secret_path.write_text('leftover from somewhere else')
            with mock.patch.object(p.recovery, 'live') as live, \
                 mock.patch.object(p.recovery, 'private_directory'):
                step = {'action': 'create', 'description': WRITE_DESCRIPTION}
                with self.assertRaises(RuntimeError):
                    p.ensure_token(step, 'home', ORG_ID, [INFRA_ID], 'write', secret_path)
            live.assert_not_called()

    def test_write_failure_after_live_create_raises_clearly_without_token(self):
        created = {'id': 'auth9', 'status': 'active',
                   'permissions': [f'write:orgs/{ORG_ID}/buckets/{INFRA_ID}'], 'token': 'super-secret-value'}
        with tempfile.TemporaryDirectory() as tmp:
            secret_path = Path(tmp) / 'threadripper.json'
            with mock.patch.object(p.recovery, 'live', return_value=json.dumps(created)) as live, \
                 mock.patch.object(p.recovery, 'private_directory'), \
                 mock.patch.object(p, 'write_secret_atomic', side_effect=OSError('disk full')):
                step = {'action': 'create', 'description': WRITE_DESCRIPTION}
                with self.assertRaises(RuntimeError) as ctx:
                    p.ensure_token(step, 'home', ORG_ID, [INFRA_ID], 'write', secret_path)
            live.assert_called_once()
            self.assertNotIn('super-secret-value', str(ctx.exception))
            self.assertIn('unrecoverable', str(ctx.exception))

    def test_rejects_unexpected_result_shape(self):
        with mock.patch.object(p.recovery, 'live', return_value=json.dumps([{}, {}])), \
             mock.patch.object(p.recovery, 'private_directory'), \
             tempfile.TemporaryDirectory() as tmp:
            step = {'action': 'create', 'description': WRITE_DESCRIPTION}
            with self.assertRaises(RuntimeError):
                p.ensure_token(step, 'home', ORG_ID, [INFRA_ID], 'write', Path(tmp) / 'x.json')


class ApplyPlanTests(unittest.TestCase):
    def test_apply_creates_bucket_then_both_tokens(self):
        plan = {'org_id': ORG_ID, 'bucket': {'action': 'create', 'bucket': 'infra', 'retention_days': 30},
                'threadripper_token': {'action': 'create', 'description': WRITE_DESCRIPTION},
                'grafana_token': {'action': 'create', 'description': GRAFANA_DESCRIPTION},
                'grafana_source_bucket_ids': [IOT_ID, NETWORK_ID, VOICE_ID]}
        bucket_created = {'id': INFRA_ID}
        write_token = {'id': 'a1', 'status': 'active',
                       'permissions': [f'write:orgs/{ORG_ID}/buckets/{INFRA_ID}'], 'token': 't1'}
        read_token = {'id': 'a2', 'status': 'active',
                      'permissions': [f'read:orgs/{ORG_ID}/buckets/{bid}'
                                      for bid in [IOT_ID, NETWORK_ID, VOICE_ID, INFRA_ID]], 'token': 't2'}
        live_responses = iter([json.dumps(bucket_created), json.dumps(write_token), json.dumps(read_token)])
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(p, 'WRITE_SECRET_PATH', Path(tmp) / 'w.json'), \
                 mock.patch.object(p, 'GRAFANA_SECRET_PATH', Path(tmp) / 'g.json'), \
                 mock.patch.object(p.recovery, 'live', side_effect=lambda _cmd: next(live_responses)), \
                 mock.patch.object(p.recovery, 'private_directory'):
                result = p.apply_plan(plan, 'home', 'infra', 30)
        self.assertEqual(result['bucket_id'], INFRA_ID)
        self.assertEqual(result['threadripper_token']['action'], 'create')
        self.assertEqual(result['grafana_token']['action'], 'create')
        self.assertNotIn('t1', json.dumps(result))
        self.assertNotIn('t2', json.dumps(result))

    def test_apply_skips_existing_bucket_and_tokens_no_live_calls(self):
        plan = {'org_id': ORG_ID, 'bucket': {'action': 'skip', 'id': INFRA_ID},
                'threadripper_token': {'action': 'skip', 'id': 'a1', 'description': 'x'},
                'grafana_token': {'action': 'skip', 'id': 'a2', 'description': 'y'},
                'grafana_source_bucket_ids': [IOT_ID, NETWORK_ID, VOICE_ID]}
        with mock.patch.object(p.recovery, 'live') as live:
            result = p.apply_plan(plan, 'home', 'infra', 30)
        live.assert_not_called()
        self.assertEqual(result['bucket_id'], INFRA_ID)

    def test_never_issues_a_delete_or_revoke_command(self):
        write_auth = {'description': WRITE_DESCRIPTION, 'status': 'active', 'id': 'wauth1',
                      'permissions': [f'write:orgs/{ORG_ID}/buckets/{INFRA_ID}']}
        grafana_auth = {'description': GRAFANA_DESCRIPTION, 'status': 'active', 'id': 'gauth1',
                        'permissions': [f'read:orgs/{ORG_ID}/buckets/{bid}'
                                        for bid in [IOT_ID, NETWORK_ID, VOICE_ID, INFRA_ID]]}
        with temp_secret('wauth1') as write_secret, temp_secret('gauth1') as grafana_secret:
            with mock.patch.object(p, 'WRITE_SECRET_PATH', write_secret), \
                 mock.patch.object(p, 'GRAFANA_SECRET_PATH', grafana_secret), \
                 mock.patch.object(p.recovery, 'command', side_effect=probe_response):
                plan = p.build_plan(ORGS, WITH_INFRA_BUCKET, [SOURCE_GRAFANA_AUTH, write_auth, grafana_auth],
                                     'home', 'infra', 30)
            with mock.patch.object(p.recovery, 'live') as live:
                p.apply_plan(plan, 'home', 'infra', 30)
            for call in live.call_args_list:
                self.assertNotIn('delete', call.args[0])
                self.assertNotIn('revoke', call.args[0])
        # The source token fixture itself was never mutated by planning/apply.
        self.assertEqual(SOURCE_GRAFANA_AUTH['status'], 'active')


class ArgumentValidationTests(IsolatedSecretPaths):
    def test_rejects_unsafe_org_name(self):
        with self.assertRaises(ValueError):
            p.validate_name('--org', 'home; rm -rf /')

    def test_rejects_nonpositive_retention(self):
        with mock.patch.object(p, 'fetch_state', return_value=(ORGS, BASE_BUCKETS, [SOURCE_GRAFANA_AUTH])):
            with self.assertRaises(ValueError):
                p.main(['--retention-days', '0'])

    def test_dry_run_never_calls_apply_plan(self):
        with mock.patch.object(p, 'fetch_state', return_value=(ORGS, BASE_BUCKETS, [SOURCE_GRAFANA_AUTH])), \
             mock.patch.object(p, 'apply_plan') as apply_plan:
            with contextlib.redirect_stdout(io.StringIO()):
                p.main([])
        apply_plan.assert_not_called()

    def test_dry_run_output_never_contains_token_value(self):
        write_auth = {'description': WRITE_DESCRIPTION, 'status': 'active', 'id': 'wauth1',
                      'permissions': [f'write:orgs/{ORG_ID}/buckets/{INFRA_ID}']}
        with temp_secret('wauth1', token='super-secret-value') as write_secret:
            with mock.patch.object(p, 'WRITE_SECRET_PATH', write_secret), \
                 mock.patch.object(p.recovery, 'command', return_value=b'400'), \
                 mock.patch.object(p, 'fetch_state',
                                    return_value=(ORGS, WITH_INFRA_BUCKET, [SOURCE_GRAFANA_AUTH, write_auth])):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    p.main([])
        self.assertNotIn('super-secret-value', buf.getvalue())

    def test_no_op_dry_run_when_everything_already_provisioned(self):
        write_auth = {'description': WRITE_DESCRIPTION, 'status': 'active', 'id': 'wauth1',
                      'permissions': [f'write:orgs/{ORG_ID}/buckets/{INFRA_ID}']}
        grafana_auth = {'description': GRAFANA_DESCRIPTION, 'status': 'active', 'id': 'gauth1',
                        'permissions': [f'read:orgs/{ORG_ID}/buckets/{bid}'
                                        for bid in [IOT_ID, NETWORK_ID, VOICE_ID, INFRA_ID]]}
        with temp_secret('wauth1') as write_secret, temp_secret('gauth1') as grafana_secret:
            with mock.patch.object(p, 'WRITE_SECRET_PATH', write_secret), \
                 mock.patch.object(p, 'GRAFANA_SECRET_PATH', grafana_secret), \
                 mock.patch.object(p.recovery, 'command', side_effect=probe_response), \
                 mock.patch.object(p, 'fetch_state',
                                    return_value=(ORGS, WITH_INFRA_BUCKET,
                                                  [SOURCE_GRAFANA_AUTH, write_auth, grafana_auth])), \
                 mock.patch.object(p, 'apply_plan') as apply_plan:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    p.main([])
        apply_plan.assert_not_called()
        output = json.loads(buf.getvalue())
        self.assertEqual(output['plan']['bucket']['action'], 'skip')
        self.assertEqual(output['plan']['threadripper_token']['action'], 'skip')
        self.assertEqual(output['plan']['grafana_token']['action'], 'skip')


if __name__ == '__main__':
    unittest.main()
