"""检查当前编辑器公开 API 和操作按钮，不写入或评测。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configuration import load_settings
from browser.session import browser_session
from educoder.challenges import inspect_assignment

settings = load_settings(Path(__file__).resolve().parents[1] / 'config.yaml')
with browser_session(settings, interactive=True) as (context, page):
    info = inspect_assignment(context, page, settings, 'C++之递归函数应用', enter=True)
    target = next(p for p in context.pages if p.url == info['current']['url'])
    print(target.evaluate('''() => ({monaco: typeof window.monaco,
      models: window.monaco?.editor?.getModels()?.map(m=>({uri:m.uri.toString(), length:m.getValue().length})),
      buttons: Array.from(document.querySelectorAll('button')).map(e=>({text:e.innerText,html:e.outerHTML})),
      controls: Array.from(document.querySelectorAll('a,span,div')).filter(e=>['评测','自测运行','测试结果'].includes(e.textContent.trim())).map(e=>e.outerHTML).slice(-15)
    })'''))
