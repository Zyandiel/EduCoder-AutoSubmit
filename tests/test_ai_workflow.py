"""流程测试使用内存题目和模拟 API，不访问真实课程或消耗额度。"""
import json
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from ai.client import AIError
from configuration import load_settings
from educoder.auto import automatic, choose_assignments
from educoder.runner import run_assignments


class AIWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / 'config.yaml'
        self.config.write_text('course_url: https://www.educoder.net/classrooms/test/shixun_homework\n', encoding='utf-8')
        self.settings = load_settings(self.config)
        self.targets = [{'name': '新增实训', 'url': f'{self.settings.course_url}/{n}/detail', 'completed': False} for n in (1, 2)]
        self.problem = {'assignment': '新增实训', 'title': '相加', 'number': 1,
                        'description': '返回两个整数之和。', 'files': [
                            {'path': 'step1/main.cpp', 'code': 'int add(int a,int b){}', 'editable': True}]}
        self.answer = {'status': 'ready', 'reason': '', 'files': [
            {'path': 'step1/main.cpp', 'code': 'int add(int a,int b){return a+b;}'}]}

    def harness(self, stack, *, result='passed', answer=None, changed=False, error=None):
        page = MagicMock()
        page.url = 'https://www.educoder.net/tasks/fixture'
        page.locator.return_value.inner_text.return_value = '评测结果'
        context = MagicMock()
        context.pages = [page]
        page.context = context
        @contextmanager
        def session(*args, **kwargs):
            yield context, page
        current = {'number': 1, 'name': '相加', 'passed': False, 'url': page.url,
                   'solution_path': str(self.root / 'absent/1.cpp')}
        inspections = {}
        def inspect(ctx, tab, settings, name, *, enter=False, detail_url=None):
            if not enter:
                inspections[detail_url] = inspections.get(detail_url, 0) + 1
            passed = inspections.get(detail_url, 0) > 1
            return {'challenges': [{'number': 1, 'passed': passed}], 'current': current}
        stack.enter_context(patch('educoder.runner.browser_session', session))
        inspect_mock = stack.enter_context(patch('educoder.runner.inspect_assignment', side_effect=inspect))
        stack.enter_context(patch('educoder.runner.move_to_pending', return_value=current))
        stack.enter_context(patch('educoder.runner.snapshot'))
        stack.enter_context(patch('educoder.runner.get_api_key', return_value='fixture-only-key'))
        model = stack.enter_context(patch('educoder.runner.DeepSeekClient')).return_value
        model.solve.return_value = self.answer if answer is None else answer
        model.solve.side_effect = error
        read = stack.enter_context(patch('educoder.runner.read_problem', return_value=self.problem))
        if changed:
            read.side_effect = [self.problem, {**self.problem, 'description': '已变化'}]
        stack.enter_context(patch('educoder.runner.MonacoEditor')).return_value.read_code.return_value = 'old code'
        write = stack.enter_context(patch('educoder.runner.write_solution', return_value=[]))
        evaluate = stack.enter_context(patch('educoder.runner.evaluate_once', return_value={'status': result, 'text': result}))
        return model, write, evaluate, inspect_mock

    def test_no_local_cpp_generates_evaluates_and_preserves_duplicate_urls(self):
        with ExitStack() as stack:
            model, write, evaluate, inspect = self.harness(stack)
            self.assertEqual(run_assignments(self.settings, self.targets), 0)
            self.assertEqual(model.solve.call_count, 2)
            self.assertEqual(evaluate.call_count, 2)
            self.assertEqual(write.call_count, 2)
            self.assertEqual({call.kwargs['detail_url'] for call in inspect.call_args_list}, {t['url'] for t in self.targets})
        self.assertFalse(self.settings.solutions_dir.exists())
        manifests = list((self.root / 'logs').glob('run-*/*/generated/1.files.json'))
        self.assertEqual(len(manifests), 2)
        self.assertEqual(json.loads(manifests[0].read_text()), {'step1/main.cpp': '1.cpp'})
        report = json.loads(next((self.root / 'logs').glob('run-*/report.json')).read_text(encoding='utf-8'))
        self.assertFalse(report['final_submission'])

    def test_failed_evaluation_once_then_next_assignment(self):
        with ExitStack() as stack:
            model, write, evaluate, _ = self.harness(stack, result='failed')
            self.assertEqual(run_assignments(self.settings, self.targets), 3)
            self.assertEqual(model.solve.call_count, 2)
            self.assertEqual(evaluate.call_count, 2)

    def test_missing_context_never_writes_or_evaluates(self):
        with ExitStack() as stack:
            model, write, evaluate, _ = self.harness(stack, answer={'status': 'needs_context', 'reason': '缺少公式', 'files': []})
            self.assertEqual(run_assignments(self.settings, self.targets), 3)
            self.assertEqual(model.solve.call_count, 2)
            write.assert_not_called()
            evaluate.assert_not_called()

    def test_template_changed_while_generating_never_writes(self):
        with ExitStack() as stack:
            _, write, evaluate, _ = self.harness(stack, changed=True)
            self.assertEqual(run_assignments(self.settings, self.targets[:1]), 3)
            write.assert_not_called()
            evaluate.assert_not_called()

    def test_fatal_api_error_stops_further_calls(self):
        with ExitStack() as stack:
            model, write, evaluate, _ = self.harness(stack, error=AIError('额度不足', fatal_run=True))
            self.assertEqual(run_assignments(self.settings, self.targets), 3)
            self.assertEqual(model.solve.call_count, 1)
            write.assert_not_called()
            evaluate.assert_not_called()

    def test_default_all_and_explicit_disabled_filter(self):
        chosen, missing = choose_assignments(self.settings, self.config, self.targets)
        self.assertEqual(chosen, self.targets)
        self.assertFalse(missing)
        with self.config.open('a', encoding='utf-8') as stream:
            stream.write('assignments:\n  - {name: 新增实训, enabled: false}\n')
        self.assertEqual(choose_assignments(self.settings, self.config, self.targets)[0], [])
        self.assertEqual(choose_assignments(self.settings, self.config, self.targets, '新增实训')[0], self.targets)

    def test_check_requires_key_without_browser_or_api(self):
        with patch('educoder.auto.get_api_key', return_value=None), patch('educoder.auto.browser_session') as browser:
            with self.assertRaisesRegex(ValueError, 'API Key'):
                automatic(self.settings, self.config, check_only=True)
            browser.assert_not_called()

    def test_all_completed_makes_no_model_calls(self):
        self.settings.session_file.parent.mkdir()
        self.settings.session_file.write_text('{}')
        (self.root / 'logs').mkdir()
        report = {'course_url': self.settings.course_url, 'scan_complete': True,
                  'assignments': [{**t, 'completed': True} for t in self.targets]}
        (self.root / 'logs/assignments.json').write_text(json.dumps(report), encoding='utf-8')
        with patch('educoder.auto.browser_session') as session, patch('educoder.auto.list_assignments', return_value=0), patch('educoder.auto.run_assignments') as run:
            session.return_value.__enter__.return_value = (None, None)
            self.assertEqual(automatic(self.settings, self.config), 0)
            run.assert_not_called()
