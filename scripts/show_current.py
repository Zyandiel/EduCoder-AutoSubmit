import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=max((root/'logs').glob('guided-*/*/spec.json'),key=lambda p:p.stat().st_mtime)
s=json.loads(p.read_text(encoding='utf-8'));d=s['description']
print(s['assignment'],s['number'],s['title'])
if len(d)>4500 and '\n编程要求\n' in d:
    intro=d.split('任务描述\n\n')[-1].split('\n相关知识\n')[0]
    print(intro+'\n'+d.rsplit('\n编程要求\n',1)[-1])
else: print(d)
print('CODE:\n'+s['code'])
print('FILES:',s.get('files',[]))
