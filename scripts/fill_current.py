"""把明确给出的代码填入最新题目模板的 Begin/End 区域。"""
import json
import re
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec_path=max((root/'logs').glob('guided-*/*/spec.json'),key=lambda p:p.stat().st_mtime)
spec=json.loads(spec_path.read_text(encoding='utf-8'))
fill=json.loads((Path(sys.argv[1]) if len(sys.argv)>1 else root/'logs/current-fill.json').read_text(encoding='utf-8'))
assert [spec['assignment'],spec['number']]==fill['target'], '当前关卡已变化'
pattern=r'(/\*+\s*Begin\s*\*+/)(.*?)(/\*+\s*End\s*\*+/)'
assert len(re.findall(pattern,spec['code'],re.S))==len(fill['blocks']), '模板区域数不符'
blocks=iter(fill['blocks'])
code=re.sub(pattern,lambda m:m[1]+'\n'+next(blocks)+'\n'+m[3],spec['code'],flags=re.S)
path=root/'solutions'/spec['assignment']/f"{spec['number']}.cpp"
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(code,encoding='utf-8')
print(path)
