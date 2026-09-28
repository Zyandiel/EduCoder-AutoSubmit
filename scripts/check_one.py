"""将指定本地解答复制到 ASCII 构建路径，做独立 C++ 语法编译。"""
import hashlib
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
source=Path(sys.argv[1]).resolve()
build=root/'logs/local-tests'/hashlib.sha256(str(source).encode()).hexdigest()[:12]
build.mkdir(parents=True,exist_ok=True)
unit=build/'unit.cpp'
unit.write_text(source.read_text(encoding='utf-8-sig'),encoding='utf-8')
for header in source.parent.glob('*.h'):
    (build/header.name).write_text(header.read_text(encoding='utf-8-sig'),encoding='utf-8')
result=subprocess.run(['g++','-std=c++11','-Wall','-Wextra','-c',str(unit),'-o',str(build/'unit.o')],capture_output=True)
print(result.stderr.decode('utf-8',errors='replace'))
print('COMPILE',source.name,result.returncode)
raise SystemExit(result.returncode)
