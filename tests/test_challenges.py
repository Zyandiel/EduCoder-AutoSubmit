import unittest
import os
import tempfile
import json
from pathlib import Path
from dataclasses import replace
from browser.session import browser_session
from configuration import load_settings
from educoder.challenges import find_assignment, move_to_pending
from educoder.challenges import parse_table, parse_current


class ChallengeTests(unittest.TestCase):
    def test_duplicate_assignment_requires_observed_detail_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config.yaml'
            course = 'https://www.educoder.net/classrooms/test/shixun_homework'
            config.write_text(f'course_url: {course}\n', encoding='utf-8')
            settings = load_settings(config)
            (root / 'logs').mkdir()
            urls = [f'{course}/{number}/detail?tabs=1' for number in (1, 2)]
            (root / 'logs/assignments.json').write_text(json.dumps({'course_url': course,
                'scan_complete': True, 'assignments': [{'name': '同名', 'url': url} for url in urls]}), encoding='utf-8')
            with self.assertRaises(ValueError):
                find_assignment(settings, '同名')
            self.assertEqual(find_assignment(settings, '同名', detail_url=urls[1]), urls[1])
            with self.assertRaises(ValueError):
                find_assignment(settings, '同名', detail_url=f'{course}/999/detail')

    def test_browser_moves_both_directions_and_rejects_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config.yaml'
            config.write_text('course_url: https://www.educoder.net/classrooms/test/shixun_homework\ndebug: false\nheadless: true\n', encoding='utf-8')
            settings = replace(load_settings(config), browser_channel=os.environ.get('EDUCODER_TEST_BROWSER', 'chromium'))
            with browser_session(settings, fresh=True) as (_, page):
                page.set_content('''<h3></h3><a href="#" onclick="render(n-1);return false">上一关</a><a href="#" onclick="render(n+1);return false">下一关</a><script>let n=3;function render(x){n=x;document.querySelector('h3').textContent='第'+n+'关：题'+n}render(3)</script>''')
                info = {'challenges': [dict(number=n, name=f'题{n}', status='未评测', passed=n != 1) for n in range(1, 4)]}
                self.assertEqual(move_to_pending(page, info, root)['number'], 1)
                info['challenges'][0]['passed'] = True
                info['challenges'][1]['passed'] = False
                self.assertEqual(move_to_pending(page, info, root)['number'], 2)
                info['challenges'][1]['passed'] = None
                with self.assertRaises(ValueError):
                    move_to_pending(page, info, root)

    def test_column_order_and_pass_status(self):
        rows = parse_table(['通过状态', '序号', '关卡名称'], [['已通过', '1', '题一'], ['未评测', '2', '题二']])
        self.assertTrue(rows[0].passed)
        self.assertFalse(rows[1].passed)
        self.assertEqual(parse_current('第2关：题二', rows).number, 2)

    def test_missing_or_duplicate_number_rejected(self):
        for nums in (['1', '1'], ['1', '3']):
            with self.assertRaises(ValueError):
                parse_table(['序号', '关卡名称', '通过状态'], [[n, '题', '未评测'] for n in nums])

    def test_mismatched_workbench_rejected(self):
        rows = parse_table(['序号', '关卡名称', '通过状态'], [['1', '题一', '未知']])
        self.assertIsNone(rows[0].passed)
        for title in ('第1关：另一题', '第2关：题一', '加载中'):
            with self.assertRaises(ValueError):
                parse_current(title, rows)
