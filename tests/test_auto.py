import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from configuration import load_settings
from educoder.auto import automatic, single_run


class AutoTests(unittest.TestCase):
    def test_lock_rejects_duplicate_and_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with single_run(root):
                with self.assertRaises(RuntimeError):
                    with single_run(root):
                        self.fail('duplicate acquired lock')
            with single_run(root):
                pass

    def test_completed_skipped_and_only_enabled_pending_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config.yaml'
            config.write_text('course_url: https://www.educoder.net/classrooms/test/shixun_homework\nassignments:\n  - {name: done, enabled: true}\n  - {name: todo, enabled: true}\n', encoding='utf-8')
            settings = load_settings(config)
            settings.session_file.parent.mkdir(parents=True)
            settings.session_file.write_text('{}')
            (root / 'logs').mkdir()
            cache = root / 'logs/assignments.json'
            for completed in (False, True):
                cache.write_text(json.dumps({'assignments': [
                    {'name': 'done', 'completed': True},
                    {'name': 'todo', 'completed': completed},
                    {'name': 'disabled', 'completed': False}]}))
                with patch('educoder.auto.check_local'), patch('educoder.auto.browser_session') as session, patch('educoder.auto.list_assignments', return_value=0), patch('educoder.auto.run_assignments', return_value=0) as run:
                    session.return_value.__enter__.return_value = (None, None)
                    self.assertEqual(automatic(settings, config), 0)
                    if completed:
                        run.assert_not_called()
                    else:
                        run.assert_called_once_with(settings, ['todo'])
            with patch('educoder.auto.browser_session') as browser:
                with self.assertRaises(ValueError):
                    automatic(replace(settings, dry_run=False), config)
                browser.assert_not_called()
