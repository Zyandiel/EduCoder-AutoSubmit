import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from browser.session import browser_session
from configuration import load_settings
from educoder.assignments import collect_assignments, parse_card


class AssignmentTests(unittest.TestCase):
    def test_progress_is_not_submission_authorization(self):
        item = parse_card({"name": "作业", "progress": "3/3", "status": "提交中"})
        self.assertTrue(item.completed)
        self.assertTrue(item.submission_window_open)
        self.assertIsNone(item.can_submit)

    def test_unknown_and_inconsistent_progress(self):
        for value in ("", "已通过", "0/0", "4/3"):
            self.assertIsNone(parse_card({"name": "作业", "progress": value}).completed)
        self.assertFalse(parse_card({"name": "作业", "progress": "1/3"}).completed)

    def test_empty_name_fails(self):
        with self.assertRaises(ValueError):
            parse_card({"name": ""})

    def test_real_browser_delayed_popup_and_pagination(self):
        # 根据观察到的卡片/分页结构制作匿名 fixture；所有请求都被拦截。
        html = '''<html><head><meta charset="utf-8"></head><body><section id="cards"></section>
<ul><li class="ant-pagination-next" aria-disabled="false" onclick="render(2)">下一页</li></ul>
<script>
function openDetail(id) {
 const child = window.open('about:blank');
 setTimeout(() => child.location.href = '/classrooms/test/shixun_homework/'+id+'/detail?tabs=1', 250);
}
function render(n) {
 document.getElementById('cards').innerHTML = `<div class="listItem___fixture">
 <span class="tag-style">提交中</span><span class="name___fixture" onclick="openDetail(${n})">作业${n}</span>
 <span><i class="icon-wanchengjindu"></i><span>${n}/2</span></span></div>`;
 document.querySelector('.ant-pagination-next').setAttribute('aria-disabled', n===2?'true':'false');
}
render(1);
</script></body></html>'''
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.yaml'
            config.write_text('course_url: https://www.educoder.net/classrooms/test/shixun_homework\ndebug: false\nheadless: true\n', encoding='utf-8')
            settings = replace(load_settings(config), browser_channel=os.environ.get('EDUCODER_TEST_BROWSER', 'chromium'))
            with browser_session(settings, fresh=True) as (context, page):
                context.route('**/*', lambda route: route.fulfill(content_type='text/html', body='<html>详情</html>' if '/detail' in route.request.url else html))
                assignments = collect_assignments(page, settings)
                self.assertEqual([item.name for item in assignments], ['作业1', '作业2'])
                self.assertTrue(all(item.url and item.error is None for item in assignments))
                self.assertEqual([item.completed for item in assignments], [False, True])
                self.assertEqual(len(context.pages), 1)
