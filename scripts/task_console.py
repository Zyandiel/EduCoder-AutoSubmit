"""逐项检查真实文件菜单；仅手动触发一次评测，无最终提交入口。"""
import json
import sys
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from configuration import load_settings
from browser.session import browser_session
from educoder.editor import MonacoEditor
from educoder.evaluator import evaluate_once
settings=load_settings(Path(__file__).resolve().parents[1]/'config.yaml')
folder=settings.root/'logs'/datetime.now().strftime('console-%Y%m%d-%H%M%S')
folder.mkdir()
with browser_session(settings,interactive=True) as (context,page):
    def log_response(response):
        request=response.request
        if request.resource_type not in ('xhr','fetch'):return
        from urllib.parse import urlsplit
        path=urlsplit(response.url).path
        entry={'method':request.method,'path':path,'status':response.status}
        if request.method in ('POST','PUT','PATCH'):
            try:
                data=request.post_data_json
                if isinstance(data,dict):
                    entry['fields']=list(data)
                    entry['file_fields']={k:v for k,v in data.items() if k in ('path','file_path','filename','file_name')}
            except Exception:pass
        with (folder/'network.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(entry,ensure_ascii=False)+'\n')
    page.on('response',log_response)
    page.goto(sys.argv[1],wait_until='domcontentloaded')
    page.locator('.monaco-editor[role="code"]:visible').wait_for(timeout=60000)
    dirty=False
    while True:
        command=input('COMMAND > ').strip()
        if command=='stop':break
        try:
            if command=='files':
                page.locator('[id^="env_"] .ant-dropdown-trigger').hover()
                page.wait_for_timeout(600)
                print(page.locator('body').inner_text(),flush=True)
                print('MENUS',page.locator('[role="menu"], [role="tree"]').evaluate_all('els=>els.map(e=>e.outerHTML)'),flush=True)
                (folder/'files.html').write_text(page.content(),encoding='utf-8')
            elif command.startswith('open '):
                page.bring_to_front()
                page.mouse.move(0,0)
                page.wait_for_timeout(250)
                page.locator('[id^="env_"] .ant-dropdown-trigger').hover()
                page.get_by_text(command[5:],exact=True).click()
                page.wait_for_timeout(700)
                print('CODE',MonacoEditor(page).read_code(),flush=True)
            elif command=='read':print('CODE',MonacoEditor(page).read_code(),flush=True)
            elif command.startswith('write '):
                path=Path(command[6:]);code=path.read_text(encoding='utf-8-sig')
                (folder/(path.name+'.before')).write_text(MonacoEditor(page).read_code(),encoding='utf-8')
                MonacoEditor(page).set_code(code)
                page.wait_for_timeout(2000)
                dirty=True
                print('WRITTEN',path,flush=True)
            elif command=='eval':
                if not dirty:raise ValueError('必须先修改代码，不重复评测。')
                dirty=False
                result=evaluate_once(page)
                print('RESULT',json.dumps(result,ensure_ascii=False),flush=True)
                (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
            elif command=='case':
                page.locator('a[class^="case-header___"]').first.click()
                print(page.locator('body').inner_text(),flush=True)
            elif command=='body':print(page.locator('body').inner_text(),flush=True)
            else:print('files / open <visible filename> / read / write <local path> / eval / case / body / stop',flush=True)
        except Exception as exc:print(type(exc).__name__,str(exc),flush=True)
        (folder/'latest.html').write_text(page.content(),encoding='utf-8')
