"""读取各作业真实详情、关卡和入口文字，供逐关开发验证。"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configuration import load_settings
from browser.session import browser_session
from educoder.challenges import inspect_assignment
from diagnostics import configure_logging, snapshot

settings = load_settings(Path(__file__).resolve().parents[1] / 'config.yaml')
configure_logging(settings.root, settings.debug)
assignments = json.loads((settings.root/'logs/assignments.json').read_text(encoding='utf-8'))['assignments']
results=[]
with browser_session(settings, interactive=True) as (context,page):
    for item in assignments:
        try:
            result=inspect_assignment(context,page,settings,item['name'])
            result['intro']=page.locator('body').inner_text()[:1600]
            result['entry_dom']=page.locator('a,button,span,div').evaluate_all("els=>els.filter(e=>['开始挑战','继续挑战','开始实训','开始学习'].includes(e.textContent.trim())).map(e=>e.outerHTML).slice(-8)")
            results.append(result)
            print('CATALOG',json.dumps(result,ensure_ascii=False),flush=True)
        except Exception as exc:
            snapshot(page,settings.root,'catalog-error')
            results.append({'assignment':item['name'],'error':type(exc).__name__})
            print('ERROR',item['name'],type(exc).__name__,flush=True)
        (settings.root/'logs/catalog.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        page.wait_for_timeout(1000)
