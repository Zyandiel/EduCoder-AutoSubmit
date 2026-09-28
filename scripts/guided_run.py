"""逐关开发验证：读取真实题目后等待终端 run；不自动生成或重试代码。"""
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from configuration import load_settings
from browser.session import browser_session
from educoder.challenges import inspect_assignment,parse_current,Challenge
from educoder.editor import MonacoEditor
from educoder.evaluator import evaluate_once
from educoder.solution_files import write_solution
from diagnostics import snapshot,configure_logging

settings=load_settings(Path(__file__).resolve().parents[1]/'config.yaml')
configure_logging(settings.root,settings.debug)
catalog=json.loads((settings.root/'logs/catalog.json').read_text(encoding='utf-8'))
root=settings.root/'logs'/datetime.now().strftime('guided-%Y%m%d-%H%M%S')
root.mkdir()
records=[]
def persist(): (root/'report.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
with browser_session(settings,interactive=True) as (context,page):
    for assignment in catalog:
        name=assignment['assignment']
        if len(sys.argv)>1 and name not in sys.argv[1:]: continue
        task=page
        try:
            info=inspect_assignment(context,page,settings,name,enter=True)
            task=next(p for p in context.pages if p.url==info['current']['url'])
            challenges=[Challenge(**c) for c in info['challenges']]
            pending=[c.number for c in challenges if c.passed is not True]
            # 平台可能恢复上次浏览的关卡；正常点击上一关回到最早未完成关卡。
            target_number=min(pending) if pending else info['current']['number']
            at=info['current']['number']
            while at>target_number:
                task.get_by_role('link',name='上一关',exact=True).click()
                at-=1
                task.locator('h3').filter(has_text=re.compile(r'^第\s*'+str(at)+r'\s*关[：:]')).wait_for(timeout=60000)
            for _ in range(len(challenges)):
                heading=task.locator('h3').filter(has_text=re.compile(r'^第\s*\d+\s*关[：:]'))
                heading.wait_for(timeout=60000)
                current=parse_current(heading.inner_text(),challenges)
                task.locator('.monaco-editor[role="code"]:visible').wait_for(timeout=60000)
                task.wait_for_timeout(1000)
                editor=MonacoEditor(task)
                original=editor.read_code()
                spec={'assignment':name,'number':current.number,'title':current.name,'url':task.url,'description':'\n'.join(task.locator('.markdown-body:visible').all_inner_texts()),'code':original}
                menu=task.locator('[id^="env_"] .ant-dropdown-trigger')
                if menu.count()==1:
                    menu.hover()
                    task.get_by_role('menuitem').first.wait_for(state='visible')
                    spec['files']=task.get_by_role('menuitem').all_inner_texts()
                    task.mouse.move(0,0)
                    task.wait_for_timeout(400)
                folder=root/f'{catalog.index(assignment)+1}-{current.number}'
                folder.mkdir(exist_ok=True)
                (folder/'spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
                (folder/'before.cpp').write_text(original,encoding='utf-8')
                solution=settings.solutions_dir/name/f'{current.number}.cpp'
                if current.passed:
                    print('SKIP_PASSED',name,current.number,flush=True)
                    if not solution.exists():
                        solution.parent.mkdir(parents=True,exist_ok=True)
                        solution.write_text(original,encoding='utf-8')
                else:
                    print('TASK_SPEC',json.dumps(spec,ensure_ascii=False),flush=True)
                    command=input('READY: write local code, then run / skip / stop > ').strip()
                    if command=='stop':raise KeyboardInterrupt()
                    if command!='run':break
                    code=solution.read_text(encoding='utf-8-sig')
                    record={'assignment':name,'number':current.number,'url':task.url,'sha256':hashlib.sha256(code.encode()).hexdigest(),'status':'writing','final_submission':False}
                    records.append(record);persist()
                    (folder/'local.cpp').write_text(code,encoding='utf-8')
                    record['files']=write_solution(task,solution,folder)
                    snapshot(task,settings.root,'guided-write-verified')
                    record['status']='evaluation_started';persist()
                    result=evaluate_once(task)
                    record.update(result);persist()
                    (folder/'result.txt').write_text(task.locator('body').inner_text(),encoding='utf-8')
                    snapshot(task,settings.root,'guided-'+result['status'])
                    print('RESULT',name,current.number,json.dumps(result,ensure_ascii=False),flush=True)
                    if result['status']!='passed':break
                if current.number==len(challenges):break
                # 已观察到成功弹层中的下一关入口；只在本关通过后使用。
                popup_next=task.locator('footer a.current').filter(has_text=re.compile(r'^下一关$'))
                if popup_next.count()==1 and popup_next.is_visible():popup_next.click()
                else:task.get_by_role('link',name='下一关',exact=True).click()
                task.locator('h3').filter(has_text=re.compile(r'^第\s*'+str(current.number+1)+r'\s*关[：:]')).wait_for(timeout=60000)
            if task!=page and not task.is_closed():task.close()
        except KeyboardInterrupt:
            print('STOPPED',flush=True);break
        except Exception as exc:
            print('GUIDED_ERROR',name,type(exc).__name__,str(exc)[:500],flush=True)
            records.append({'assignment':name,'status':'error','error':str(exc)[:500]});persist()
            if not context.pages:
                print('浏览器已关闭，进度已保存；重新运行可继续。',flush=True)
                break
            target=context.pages[-1]
            snapshot(target,settings.root,'guided-error')
            (root/f'error-{catalog.index(assignment)}.txt').write_text(target.locator('body').inner_text(),encoding='utf-8')
            (settings.root/'debug/guided-error.html').write_text(target.content(),encoding='utf-8')
    print('GUIDED_REPORT',root,flush=True)
