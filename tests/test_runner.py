import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch
from configuration import load_settings
from educoder.runner import run_assignments


class RunnerTests(unittest.TestCase):
    def test_missing_pending_code_stops_before_workbench(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config.yaml'
            config.write_text('course_url: https://www.educoder.net/classrooms/test/shixun_homework\n', encoding='utf-8')
            settings = load_settings(config)
            files = settings.solutions_dir / '示例'
            files.mkdir(parents=True)
            (files / '2.cpp').write_text('existing user code', encoding='utf-8')
            @contextmanager
            def session(*args, **kwargs):
                yield MagicMock(), MagicMock()
            with patch('educoder.runner.browser_session', session), patch('educoder.runner.inspect_assignment', return_value={'challenges': [{'number': 2, 'passed': True}, {'number': 3, 'passed': False}]}) as inspect, patch('educoder.runner.MonacoEditor') as editor, patch('educoder.runner.evaluate_once') as evaluate:
                self.assertEqual(run_assignments(settings, ['示例']), 3)
                inspect.assert_called_once()
                editor.assert_not_called()
                evaluate.assert_not_called()
            report = json.loads(next((root / 'logs').glob('run-*/report.json')).read_text(encoding='utf-8'))
            self.assertEqual(report['items'][0]['status'], 'missing_solution')
            self.assertFalse(report['final_submission'])
