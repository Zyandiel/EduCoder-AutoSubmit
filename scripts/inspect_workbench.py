"""按已读取的详情链接发现工作区 DOM；不修改代码或评测。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from browser.session import browser_session
from browser.navigation import navigate
from configuration import load_settings
from diagnostics import configure_logging, snapshot


def main():
    settings = load_settings(Path(__file__).resolve().parents[1] / 'config.yaml')
    configure_logging(settings.root, settings.debug)
    report = json.loads((settings.root / 'logs/assignments.json').read_text(encoding='utf-8'))
    item = next(a for a in report['assignments'] if a['name'] == 'C++之递归函数应用')
    with browser_session(settings, interactive=True) as (context, page):
        navigate(page, item['url'], settings)
        page.get_by_text('继续挑战', exact=True).wait_for(timeout=settings.navigation_timeout_ms)
        print('TABLES', page.locator('table').evaluate_all('els => els.map(e => e.outerHTML)'))
        if '--enter' not in sys.argv:
            return
        page.get_by_text('继续挑战', exact=True).click()
        page.wait_for_timeout(10000)
        target = context.pages[-1]
        print('URL', target.url)
        print('TEXT', target.locator('body').inner_text()[:14000])
        print('FRAMES', [frame.url for frame in target.frames])
        snapshot(target, settings.root, 'workbench-discovery')
        (settings.root / 'debug/workbench.html').write_text(target.content(), encoding='utf-8')


if __name__ == '__main__':
    main()
