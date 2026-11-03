"""Synthetic browser fixtures for the observed workspace DOM, not site mocks."""
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from browser.session import browser_session
from configuration import load_settings
from educoder.workspace import _path, _selected, read_problem, select_file


FIXTURE = '''<h3>第1关：求和</h3>
<div class="markdown-body">编程要求：实现 add(int,int)。请保留函数签名。</div>
<div id="env_1"><button class="ant-dropdown-trigger" onmouseover="menu.hidden=false">代码文件</button></div>
<ul id="menu" hidden>
<li role="menuitem" onclick="choose('step1/add.cpp')">step1/add.cpp</li>
<li role="menuitem" onclick="choose('step1/add.h')">step1/add.h</li>
</ul>
<div class="monaco-editor" role="code" data-uri="inmemory://model/1">
<textarea class="inputarea" rows="4">int add(int a,int b){return 0;}</textarea></div>
<script>
const files = {'step1/add.cpp':'int add(int a,int b){return 0;}',
               'step1/add.h':'int add(int a,int b);'};
let chosen = 'step1/add.cpp', model = 1, renderDelay = 250;
const root = document.querySelector('[role=code]');
function choose(path) {
  menu.hidden = true;
  if (path === chosen) return;
  setTimeout(() => {
    chosen = path;
    root.setAttribute('data-uri', 'inmemory://model/' + (++model));
    root.querySelector('textarea').value = files[path];
    root.querySelector('textarea').readOnly = path.endsWith('.h');
  }, renderDelay);
}
</script>'''


class WorkspacePathTests(unittest.TestCase):
    def test_source_paths_only_no_normalization_or_traversal(self):
        for value in ('step1/main.cpp', 'step1/接口.hpp', 'file.h'):
            self.assertEqual(_path(value), value)
        for value in ('', ' step/a.cpp', '/root.cpp', '../secret.h', 'step/../a.cpp',
                      'C:/a.cpp', 'step\\a.cpp', 'step//a.cpp', 'step/./a.cpp',
                      'step/a.cpp\n', 'main.exe'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _path(value)


class WorkspaceBrowserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        config = root / 'config.yaml'
        config.write_text('course_url: https://www.educoder.net/classrooms/test/shixun_homework\n'
                          'debug: false\nheadless: true\n', encoding='utf-8')
        settings = replace(load_settings(config), browser_channel=os.environ.get('EDUCODER_TEST_BROWSER', 'chromium'))
        self.session = browser_session(settings, fresh=True)
        _, self.page = self.session.__enter__()
        self.page.set_content(FIXTURE)
        self.reader = patch('educoder.workspace.MonacoEditor.read_code',
                            lambda editor: editor.input.input_value())
        self.reader.start()
        self.current = {'number': 1, 'name': '求和', 'passed': False}

    def tearDown(self):
        self.reader.stop()
        self.session.__exit__(None, None, None)
        self.temp.cleanup()

    def test_reads_full_problem_and_each_file_with_readonly_flag(self):
        result = read_problem(self.page, assignment='C++', current=self.current)
        self.assertEqual(result['title'], '求和')
        self.assertEqual([file['path'] for file in result['files']], ['step1/add.cpp', 'step1/add.h'])
        self.assertEqual(result['files'][0]['code'], 'int add(int a,int b){return 0;}')
        self.assertTrue(result['files'][0]['editable'])
        self.assertEqual(result['files'][1]['code'], 'int add(int a,int b);')
        self.assertFalse(result['files'][1]['editable'])
        self.assertNotIn('url', result)
        self.assertNotIn('cookies', result)
        # Reading again starts from the last selected file, not an assumed tab.
        self.assertEqual(read_problem(self.page, assignment='C++', current=self.current), result)

    def test_unknown_file_and_changed_heading_stop(self):
        with self.assertRaises(ValueError):
            select_file(self.page, 'step1/not-in-menu.cpp')
        self.page.locator('h3').evaluate('(e)=>e.textContent="第2关：其他题"')
        with self.assertRaises(ValueError):
            read_problem(self.page, assignment='C++', current=self.current)

    def test_fresh_nonfirst_model_never_bound_to_requested_first_file(self):
        # The old implementation accepted the stable header after 0.7 s even
        # though choosing the source needed 1.5 s. A probe already showing the
        # header now gives no identity proof and must fail without reading it.
        self.page.evaluate('''() => {
            chosen = 'step1/add.h'; renderDelay = 1500;
            root.querySelector('textarea').value = files[chosen];
            root.querySelector('textarea').readOnly = true;
        }''')
        with patch('educoder.workspace._MODEL_CHANGE_TIMEOUT_MS', 500):
            with self.assertRaisesRegex(ValueError, '模型未更新'):
                select_file(self.page, 'step1/add.cpp')
        self.assertIsNone(_selected.get(self.page))
        self.assertEqual(self.page.locator('textarea').input_value(), 'int add(int a,int b);')

    def test_fresh_default_model_waits_for_both_delayed_transitions(self):
        self.page.evaluate('renderDelay = 1500')
        select_file(self.page, 'step1/add.cpp')
        self.assertEqual(_selected[self.page][1], 'step1/add.cpp')
        self.assertEqual(self.page.locator('textarea').input_value(),
                         'int add(int a,int b){return 0;}')
        self.assertEqual(self.page.locator('[role=code]').get_attribute('data-uri'),
                         'inmemory://model/3')

    def test_missing_or_ambiguous_description_and_limit_stop(self):
        with self.assertRaises(ValueError):
            read_problem(self.page, assignment='C++', current=self.current, max_chars=10)
        self.page.locator('.markdown-body').evaluate('(e)=>e.after(e.cloneNode(true))')
        with self.assertRaises(ValueError):
            read_problem(self.page, assignment='C++', current=self.current)

    def test_refuses_duplicate_file_menu(self):
        self.page.locator('[role=menuitem]').first.evaluate('(e)=>e.after(e.cloneNode(true))')
        with self.assertRaises(ValueError):
            read_problem(self.page, assignment='C++', current=self.current)


if __name__ == '__main__':
    unittest.main()
