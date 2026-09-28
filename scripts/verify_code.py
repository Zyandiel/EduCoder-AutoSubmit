"""阶段五、六的一次性实测。先完整备份/校验，再单次评测并记录真实 DOM。"""
import json
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configuration import load_settings
from browser.session import browser_session
from educoder.challenges import inspect_assignment
from educoder.editor import MonacoEditor
from diagnostics import snapshot

settings = load_settings(Path(__file__).resolve().parents[1] / 'config.yaml')
folder = settings.root / 'logs' / datetime.now().strftime('run-%Y%m%d-%H%M%S')
folder.mkdir(parents=True)
with browser_session(settings, interactive=True) as (context, page):
    try:
        info = inspect_assignment(context, page, settings, 'C++之递归函数应用', enter=True)
        current = info['current']
        page = next(p for p in context.pages if p.url == current['url'])
        if current['number'] != 2 or current['passed'] is not False:
            raise ValueError('当前关卡不是待评测的第 2 关，停止实测。')
        code = Path(current['solution_path']).read_text(encoding='utf-8-sig')
        (folder / 'local.cpp').write_text(code, encoding='utf-8')
        (folder / 'context.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
        editor = MonacoEditor(page)
        (folder / 'before.cpp').write_text(editor.read_code(), encoding='utf-8')
        editor.set_code(code)
        print('WRITE_VERIFIED')
        snapshot(page, settings.root, 'code-written-verified')
        button = page.locator('button[title="运行评测"]')
        if button.count() != 1:
            raise ValueError('评测按钮不唯一。')
        (folder / 'evaluation-started.txt').write_text('单次点击评测；尚未确认结果', encoding='utf-8')
        button.click()
        page.wait_for_timeout(15000)
        (folder / 'result.txt').write_text(page.locator('body').inner_text(), encoding='utf-8')
        (settings.root / 'debug/evaluation.html').write_text(page.content(), encoding='utf-8')
        snapshot(page, settings.root, 'evaluation-discovery')
        print(page.locator('body').inner_text()[-7000:])
        print('LOG_DIR', folder)
    except Exception as exc:
        (folder / 'error.txt').write_text(f'{type(exc).__name__}: {exc}', encoding='utf-8')
        snapshot(page, settings.root, 'code-verification-error')
        raise
