import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from configuration import load_settings
from browser.session import browser_session
settings=load_settings(Path(__file__).resolve().parents[1]/'config.yaml')
with browser_session(settings,interactive=True) as (context,page):
    page.goto(sys.argv[1],wait_until='domcontentloaded')
    page.locator('.monaco-editor[role="code"]:visible').wait_for(timeout=60000)
    page.wait_for_timeout(2000)
    if '--reference' in sys.argv:
        page.get_by_text('参考答案',exact=True).click()
        page.wait_for_timeout(1000)
        print('REFERENCE_PANEL',page.locator('body').inner_text())
        print('DIALOGS',page.locator('[role="dialog"]').evaluate_all('els=>els.map(e=>e.outerHTML)'))
        (settings.root/'debug/reference-panel.html').write_text(page.content(),encoding='utf-8')
        raise SystemExit(0)
    print(page.locator('body').inner_text())
    print('TREE',page.locator('[role="tree"]').evaluate_all('els=>els.map(e=>e.outerHTML)'))
    print('CASES',page.locator('a[class^="case-header___"]').evaluate_all('els=>els.map(e=>e.outerHTML)'))
    for case in page.locator('a[class^="case-header___"]').all()[:1]:
        case.click()
        print('EXPANDED',page.locator('body').inner_text())
    (settings.root/'debug/inspect-task.html').write_text(page.content(),encoding='utf-8')
