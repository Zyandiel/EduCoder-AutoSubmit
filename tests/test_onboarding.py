import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from configuration import load_settings
from onboarding import course_from_url, initialize_config, prepare_start


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # Windows CI may return an 8.3 short path (RUNNER~1), while configuration
        # normalizes it to the long path. Compare the same canonical directory.
        self.root = Path(temporary.name).resolve()
        self.config = self.root / 'config.local.yaml'
        browser = patch('onboarding.ensure_browser', side_effect=lambda settings, path: settings)
        browser.start()
        self.addCleanup(browser.stop)

    def test_course_capture_accepts_only_real_course_path(self):
        actual = 'https://www.educoder.net/classrooms/DEMO/shixun_homework'
        self.assertEqual(course_from_url(actual + '?page=2#here'), actual)
        for url in ('https://www.educoder.net.evil.invalid/classrooms/D/shixun_homework',
                    'http://www.educoder.net/classrooms/D/shixun_homework',
                    'https://user@www.educoder.net/classrooms/D/shixun_homework',
                    actual + '/123/detail', 'https://www.educoder.net/tasks/123'):
            self.assertIsNone(course_from_url(url))

    def test_first_start_without_solutions_or_config_captures_course(self):
        context, page = MagicMock(), MagicMock()
        page.url = 'https://www.educoder.net/classrooms/DEMO/shixun_homework?page=2'
        context.pages = [page]
        @contextmanager
        def session(*args, **kwargs):
            yield context, page
        with patch('onboarding.get_api_key', return_value=None), patch('onboarding.configure_api_key') as key, patch('onboarding.browser_session', session), patch('onboarding.navigate'), patch('onboarding.save_state') as save, patch('builtins.input', return_value=''):
            settings = prepare_start(self.config)
            key.assert_called_once_with(self.root)
            save.assert_called_once_with(context, settings.session_file)
        self.assertEqual(settings.course_url, page.url.split('?')[0])
        self.assertTrue(settings.ai.enabled)
        self.assertFalse(settings.solutions_dir.exists())
        self.assertNotIn('api_key', self.config.read_text(encoding='utf-8'))

    def test_reuse_config_and_encrypted_key_has_no_interaction(self):
        initialize_config(self.config)
        data = yaml.safe_load(self.config.read_text(encoding='utf-8'))
        data['course_url'] = 'https://www.educoder.net/classrooms/DEMO/shixun_homework'
        self.config.write_text(yaml.safe_dump(data), encoding='utf-8')
        with patch('onboarding.get_api_key', return_value='existing-key'), patch('onboarding.configure_api_key') as key, patch('onboarding.capture_course') as capture:
            prepare_start(self.config)
            key.assert_not_called()
            capture.assert_not_called()

    def test_invalid_ai_config_rejected_before_any_network(self):
        for extra in ('ai: {enabled: "true"}', 'ai: {max_calls_per_run: 0}',
                      'ai: {api_key: secret}', 'assignment_scope: unknown'):
            self.config.write_text('course_url: https://www.educoder.net/classrooms/test/shixun_homework\n' + extra, encoding='utf-8')
            with self.assertRaises(ValueError):
                load_settings(self.config)
