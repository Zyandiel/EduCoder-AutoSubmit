"""通过题目页面及真实上一关/下一关链接收集要求和框架；不评测。"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configuration import load_settings
from browser.session import browser_session
from educoder.challenges import inspect_assignment, parse_current, Challenge
from educoder.editor import MonacoEditor
from diagnostics import configure_logging, snapshot

settings=load_settings(Path(__file__).resolve().parents[1]/'config.yaml')
configure_logging(settings.root,settings.debug)
catalog=json.loads((settings.root/'logs/catalog.json').read_text(encoding='utf-8'))
out=settings.root/'logs/task_specs.json'
specs=json.loads(out.read_text(encoding='utf-8')) if out.exists() else []
def save():out.write_text(json.dumps(specs,ensure_ascii=False,indent=2),encoding='utf-8')
def link(page,text):
    loc=page.get_by_role('link',name=text,exact=True)
    return urljoin(page.url,loc.get_attribute('href')) if loc.count()==1 and loc.get_attribute('href') else None
with browser_session(settings,interactive=True) as (context,page):
    for assignment in catalog:
        name=assignment['assignment']
        if len(sys.argv)>1 and name!=sys.argv[1]:continue
        if len([s for s in specs if s['assignment']==name])==len(assignment['challenges']):continue
        try:
            info=inspect_assignment(context,page,settings,name,enter=True)
            task=next(p for p in context.pages if p.url==info['current']['url'])
            challenges=[Challenge(**c) for c in info['challenges']]
            for _ in range(len(challenges)):
                h=task.locator('h3').filter(has_text=re.compile(r'^第\s*\d+\s*关[：:]'))
                h.wait_for(timeout=60000)
                current=parse_current(h.inner_text(),challenges)
                if current.number==1:break
                previous=link(task,'上一关')
                if not previous:raise ValueError('缺少真实上一关链接')
                task.get_by_role('link',name='上一关',exact=True).click()
                task.locator('h3').filter(has_text=re.compile(r'^第\s*'+str(current.number-1)+r'\s*关[：:]')).wait_for(timeout=60000)
            seen=set()
            for _ in range(len(challenges)):
                h=task.locator('h3').filter(has_text=re.compile(r'^第\s*\d+\s*关[：:]'))
                h.wait_for(timeout=60000)
                current=parse_current(h.inner_text(),challenges)
                if current.number in seen:raise ValueError('关卡导航重复')
                seen.add(current.number)
                task.locator('.monaco-editor[role="code"]:visible').wait_for(timeout=60000)
                task.wait_for_timeout(600)
                description=task.locator('.markdown-body:visible').all_inner_texts()
                code=MonacoEditor(task).read_code()
                record={'assignment':name,'number':current.number,'title':current.name,'url':task.url,'description':'\n'.join(description),'code':code,'next_url':link(task,'下一关'),'previous_url':link(task,'上一关')}
                specs=[s for s in specs if (s['assignment'],s['number'])!=(name,current.number)]+[record]
                save()
                print('CAPTURED',name,current.number,current.name,flush=True)
                # 站点部分实训禁止跳关。尚未通过时只收集当前关卡，不尝试下一关。
                if not current.passed:
                    break
                if current.number==len(challenges):break
                if not record['next_url']:raise ValueError('缺少真实下一关链接')
                task.get_by_role('link',name='下一关',exact=True).click()
                task.locator('h3').filter(has_text=re.compile(r'^第\s*'+str(current.number+1)+r'\s*关[：:]')).wait_for(timeout=60000)
            if task!=page:task.close()
        except Exception as exc:
            print('CAPTURE_ERROR',name,type(exc).__name__,str(exc)[:300],flush=True)
            for i,tab in enumerate(context.pages):
                if not tab.is_closed():
                    snapshot(tab,settings.root,f'spec-error-{i}')
                    (settings.root/f'debug/spec-error-{i}.html').write_text(tab.content(),encoding='utf-8')
                    (settings.root/f'logs/spec-error-{i}.txt').write_text(tab.locator('body').inner_text(),encoding='utf-8')
            break
