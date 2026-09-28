import tempfile
import os
from dataclasses import replace
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from browser.session import browser_session, login, read_state, save_state
from configuration import load_settings
from main import main


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = self.root / "config.yaml"
        self.config.write_text('course_url: "https://www.educoder.net/classrooms/test/shixun_homework"\ndebug: false\nheadless: true\n', encoding="utf-8")
        self.settings = load_settings(self.config)
        self.settings = replace(self.settings, browser_channel=os.environ.get("EDUCODER_TEST_BROWSER", "chromium"))

    def test_safe_defaults_and_disabled_submission(self):
        self.assertTrue(self.settings.dry_run)
        with patch("main.browser_session") as browser, patch("main.configure_logging"):
            self.assertEqual(main(["--config", str(self.config), "submit"]), 2)
            browser.assert_not_called()

    def test_invalid_yaml_and_boolean(self):
        for text in ('[broken', 'dry_run: "false"'):
            self.config.write_text(text, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_settings(self.config)

    def test_corrupt_state_rejected(self):
        self.settings.session_file.parent.mkdir()
        self.settings.session_file.write_text("broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            read_state(self.settings.session_file)

    def test_failed_save_preserves_previous_session(self):
        class Context:
            def storage_state(self, **kwargs):
                return {"cookies": [], "origins": []}
        path = self.settings.session_file
        path.parent.mkdir()
        path.write_text("original", encoding="utf-8")
        with patch("browser.session.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                save_state(Context(), path)
        self.assertEqual(path.read_text(), "original")
        self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_login_requires_explicit_save(self):
        context = MagicMock()
        page = MagicMock()
        context.pages = [page]
        @contextmanager
        def fixture(*args, **kwargs):
            yield context, page
        with patch("browser.session.browser_session", fixture), patch("browser.session.navigate"), patch("browser.session.save_state") as save:
            with patch("builtins.input", side_effect=["", "yes", "q"]):
                login(self.settings)
            save.assert_not_called()
            with patch("builtins.input", return_value="save"):
                login(self.settings)
            save.assert_called_once_with(context, self.settings.session_file)

    def test_browser_storage_roundtrip(self):
        # 真实 Chromium，拦截测试域名以避免向任何外部网站发请求。
        url = "https://session-test.invalid/"
        with browser_session(self.settings, fresh=True) as (context, page):
            page.route("**/*", lambda route: route.fulfill(body="<html><title>Session fixture</title></html>", content_type="text/html"))
            page.goto(url)
            page.evaluate("localStorage.setItem('fixture', 'restored')")
            context.add_cookies([{"name": "fixture", "value": "restored", "url": url}])
            save_state(context, self.settings.session_file)
        with browser_session(self.settings) as (context, page):
            page.route("**/*", lambda route: route.fulfill(body="<html></html>", content_type="text/html"))
            page.goto(url)
            self.assertEqual(page.evaluate("localStorage.getItem('fixture')"), "restored")
            self.assertTrue(any(cookie["name"] == "fixture" for cookie in context.cookies()))


if __name__ == "__main__":
    unittest.main()
