"""通过页面正常文件菜单读取可编辑文件模板，不发起评测。"""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from configuration import load_settings
from browser.session import browser_session
from educoder.editor import MonacoEditor
settings=load_settings(Path(__file__).resolve().parents[1]/'config.yaml')
with browser_session(settings,interactive=True) as (context,page):
    page.goto(sys.argv[1],wait_until='domcontentloaded')
    page.locator('.monaco-editor[role="code"]:visible').wait_for(timeout=60000)
    page.locator('[id^="env_"] .ant-dropdown-trigger').hover()
    page.get_by_role('menuitem').first.wait_for(state='visible')
    names=page.get_by_role('menuitem').all_inner_texts()
    files={}
    for name in names:
        page.bring_to_front()
        page.mouse.move(0,0)
        page.wait_for_timeout(250)
        page.locator('[id^="env_"] .ant-dropdown-trigger').hover()
        page.get_by_role('menuitem',name=name,exact=True).click()
        page.wait_for_timeout(700)
        files[name]=MonacoEditor(page).read_code()
        print(name+'\n'+files[name],flush=True)
    (settings.root/'logs/current-task-files.json').write_text(json.dumps(files,ensure_ascii=False,indent=2),encoding='utf-8')
