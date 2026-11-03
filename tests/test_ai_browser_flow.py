"""真实 Chrome/Chromium + 合成课程 DOM + 模拟 API 响应；不访问外部站点。"""
import io
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from configuration import load_settings
from browser.session import browser_session
from educoder.editor import MonacoEditor
from educoder.runner import run_assignments
from test_workspace import FIXTURE


class AIBrowserFlowTests(unittest.TestCase):
    def test_monaco_api_reads_empty_model_by_exact_uri(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.yaml'
            config.write_text('course_url: https://www.educoder.net/classrooms/test/shixun_homework\n'
                              'debug: false\nheadless: true\n', encoding='utf-8')
            settings = replace(load_settings(config), browser_channel=os.environ.get('EDUCODER_TEST_BROWSER', 'chromium'))
            with browser_session(settings, fresh=True) as (_, page):
                page.set_content('''<div class="monaco-editor" role="code" data-uri="inmemory://model/2">
                <textarea class="inputarea"></textarea></div><script>
                window.monaco={editor:{getModels:()=>[
                  {uri:{toString:()=> 'inmemory://model/1'},getValue:()=> 'wrong file'},
                  {uri:{toString:()=> 'inmemory://model/2'},getValue:()=> ''}
                ]}};</script>''')
                self.assertEqual(MonacoEditor(page).read_code(), '')
                page.locator('textarea').evaluate("e=>e.setAttribute('aria-readonly','true')")
                with self.assertRaisesRegex(ValueError, '只读'):
                    MonacoEditor(page).set_code('int x;')

    def test_empty_solutions_to_generated_code_verified_and_evaluated_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config.yaml'
            config.write_text('course_url: https://www.educoder.net/classrooms/test/shixun_homework\n'
                              'debug: false\nheadless: true\n', encoding='utf-8')
            settings = replace(load_settings(config), browser_channel=os.environ.get('EDUCODER_TEST_BROWSER', 'chromium'))
            code = 'int add(int a,int b){return a+b;}\n'
            fixture = FIXTURE + '''<button title="运行评测">评测</button>
            <div class="test-set-container___fixture"><section></section></div><script>
            window.evaluations=0;
            root.querySelector('textarea').addEventListener('input', e=>files[chosen]=e.target.value);
            document.querySelector('button[title="运行评测"]').onclick=()=>{
              window.evaluations++;
              if(window.evaluations !== 1) throw Error('repeated evaluation');
              const pass = files['step1/add.cpp'].includes('return a+b;');
              setTimeout(()=>document.querySelector('section').innerHTML=pass
                ? '<p class="test-result success">1/1 全部通过</p>'
                : '<p class="test-result">0/1 未通过</p>',100);
            };
            </script>'''
            seen = []
            def inspect(context, page, options, name, *, enter=False, detail_url=None):
                if not enter:
                    seen.append(detail_url)
                passed = len(seen) > 1
                info = {'challenges': [{'number': 1, 'passed': passed}]}
                if enter:
                    page.route('**/*', lambda route: route.fulfill(body=fixture, content_type='text/html; charset=utf-8'))
                    page.goto('https://workflow-test.invalid/tasks/one')
                    info['current'] = {'number': 1, 'name': '求和', 'url': page.url,
                                       'passed': False, 'solution_path': str(root / 'absent.cpp')}
                return info
            response = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({
                'status': 'ready', 'reason': '完成求和', 'files': [{'path': 'step1/add.cpp', 'code': code}]})}}]}
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(response).encode())
            with patch('educoder.runner.inspect_assignment', side_effect=inspect), \
                 patch('educoder.runner.move_to_pending', side_effect=lambda page, info, directory: info['current']), \
                 patch('educoder.runner.get_api_key', return_value='fixture-only-key'), \
                 patch('educoder.runner.snapshot'), \
                 patch('ai.client.urllib.request.build_opener', return_value=opener):
                result = run_assignments(settings, [{'name': '测试求和', 'url': settings.course_url + '/1/detail'}])
            report = json.loads(next((root / 'logs').glob('run-*/report.json')).read_text(encoding='utf-8'))
            self.assertEqual(result, 0, report)
            self.assertEqual(report['items'][0]['status'], 'passed')
            self.assertEqual(report['items'][1]['status'], 'already_completed')
            self.assertFalse(report['final_submission'])
            self.assertFalse(settings.solutions_dir.exists())
            opener.open.assert_called_once()
            local = next((root / 'logs').glob('run-*/*/generated/1.cpp'))
            self.assertEqual(local.read_text(encoding='utf-8'), code)
