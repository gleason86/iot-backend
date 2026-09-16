from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('monitor', Path(__file__).resolve().parents[1] / 'scripts/continuity-monitor.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

try:
    import jinja2
    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False

SERVICE_TEMPLATE = Path(__file__).resolve().parents[1] / 'roles/monitor/templates/continuity-monitor.service.j2'


class MonitorTests(unittest.TestCase):
    def test_three_samples_required_for_failure_and_recovery(self):
        now = datetime.now(timezone.utc)
        state = {'status': 'healthy'}
        for count in range(1, 4):
            state = m.transition(state, ['backend'], now)
            self.assertEqual(state['status'], 'failed' if count == 3 else 'healthy')
        for count in range(1, 4):
            state = m.transition(state, [], now)
            self.assertEqual(state['status'], 'healthy' if count == 3 else 'failed')
        self.assertEqual(state['promotion'], 'disabled')

    def test_intermittent_success_resets_failure_streak(self):
        now = datetime.now(timezone.utc)
        state = m.transition({}, ['backend'], now)
        state = m.transition(state, [], now)
        state = m.transition(state, ['backend'], now)
        self.assertEqual(state['consecutive'], 1)
        self.assertEqual(state['status'], 'unknown')

    def test_freshness_thresholds_unchanged(self):
        # Guards against the endpoint-allowlist change accidentally touching
        # producer freshness behaviour, which is out of scope for this fix.
        self.assertEqual(m.THRESHOLDS, {
            'iot:W': 900, 'network:cable_modem': 1020, 'network:wifi_ap': 1020,
            'network:starlink_dish': 300, 'network:orbi_unit': 300,
            'network:router_wan': 300, 'network:router_port': 300, 'network:router_system': 300,
        })


class EndpointAllowlistTests(unittest.TestCase):
    def test_allowed_urls_are_exactly_cable_and_legacy(self):
        self.assertEqual(set(m.ALLOWED_URLS),
                          {'http://10.77.77.1:8086', 'http://192.168.1.100:8086'})

    def test_validate_url_accepts_cable_and_legacy(self):
        m.validate_url('http://10.77.77.1:8086')
        m.validate_url('http://192.168.1.100:8086')

    def test_validate_url_rejects_anything_else(self):
        for bad in ('http://10.77.77.1:8087', 'https://10.77.77.1:8086',
                    'http://10.77.77.2:8086', 'http://192.168.1.100:1883',
                    'http://192.168.1.101:8086', '', 'http://10.77.77.1:8086/'):
            with self.assertRaises(ValueError):
                m.validate_url(bad)


@unittest.skipUnless(HAS_JINJA2, 'jinja2 not installed locally; rendering is verified in the disposable validation container')
class RenderIPAddressAllowTests(unittest.TestCase):
    def render(self, context):
        return jinja2.Template(SERVICE_TEMPLATE.read_text()).render(**context)

    def test_default_ip_allow_covers_both_allowlisted_hosts_without_vars(self):
        # Mirrors tests/render.yml, which templates this file without loading
        # roles/monitor/defaults; the template's own default must still match
        # the two hosts in scripts/continuity-monitor.py's ALLOWED_URLS.
        rendered = self.render({})
        self.assertIn('IPAddressAllow=10.77.77.1 192.168.1.100', rendered)

    def test_ip_allow_is_driven_by_the_configured_variable(self):
        rendered = self.render({'monitor_endpoint_hosts': ['10.77.77.1']})
        self.assertIn('IPAddressAllow=10.77.77.1', rendered)
        self.assertNotIn('192.168.1.100', rendered)


if __name__ == '__main__': unittest.main()
