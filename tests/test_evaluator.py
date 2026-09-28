import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from configuration import load_settings
from browser.session import browser_session
from educoder.evaluator import classify_result, evaluate_once


class EvaluatorTests(unittest.TestCase):
    def test_conservative_success(self):
        self.assertEqual(classify_result('10/10 全部通过', 'test-result success'), 'passed')
        for text, cls in [('0/0 全部通过', 'success'), ('10/10 全部通过', ''), ('10/10', 'success'), ('任务描述 Success', 'success')]:
            self.assertEqual(classify_result(text, cls), 'unknown')
        self.assertEqual(classify_result('9/10', 'test-result'), 'failed')

    def test_fresh_result_and_no_retries_or_stale_success(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.yaml'
            config.write_text('course_url: https://www.educoder.net/classrooms/test/shixun_homework\ndebug: false\nheadless: true\n', encoding='utf-8')
            settings = replace(load_settings(config), browser_channel=os.environ.get('EDUCODER_TEST_BROWSER', 'chromium'))
            with browser_session(settings, fresh=True) as (_, page):
                page.set_content('''<meta charset="utf-8"><button title="运行评测">评测</button><div class="test-set-container___fixture"><section></section></div><script>window.clicks=0;
                  document.querySelector('button').onclick=()=>{window.clicks++;setTimeout(()=>document.querySelector('section').innerHTML='<p class="test-result success">10/10 全部通过</p>',100);};
                </script>''')
                self.assertEqual(evaluate_once(page, 2000)['status'], 'passed')
                self.assertEqual(page.evaluate('window.clicks'), 1)
                page.locator('button').evaluate("e => e.setAttribute('onclick', 'window.clicks++')")
                with self.assertRaises(PlaywrightTimeout):
                    evaluate_once(page, 300)
                self.assertEqual(page.evaluate('window.clicks'), 2)
