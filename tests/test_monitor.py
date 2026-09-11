from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('monitor', Path(__file__).resolve().parents[1] / 'scripts/continuity-monitor.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


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


if __name__ == '__main__': unittest.main()
