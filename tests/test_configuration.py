import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from configuration import default_config, load_settings
from main import main


class ConfigurationTests(unittest.TestCase):
    def test_init_preserves_edits_and_template_requires_real_course(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.local.yaml'
            with patch('main.default_config', return_value=path):
                self.assertEqual(main(['init']), 0)
                self.assertTrue(load_settings(path).dry_run)
                with patch('main.browser_session') as browser, patch('main.configure_logging'):
                    self.assertEqual(main(['list']), 1)
                    self.assertEqual(main(['inspect', '--assignment', '示例实训']), 1)
                    self.assertEqual(main(['auto']), 1)
                    browser.assert_not_called()
                path.write_text('user edits', encoding='utf-8')
                self.assertEqual(main(['init']), 0)
                self.assertEqual(path.read_text(encoding='utf-8'), 'user edits')

    def test_local_config_preferred_and_legacy_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(default_config(root).name, 'config.local.yaml')
            (root / 'config.yaml').write_text('legacy', encoding='utf-8')
            self.assertEqual(default_config(root).name, 'config.yaml')
            (root / 'config.local.yaml').write_text('local', encoding='utf-8')
            self.assertEqual(default_config(root).name, 'config.local.yaml')

    def test_missing_config_has_setup_hint(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'main.py init'):
                load_settings(Path(directory) / 'missing.yaml')
