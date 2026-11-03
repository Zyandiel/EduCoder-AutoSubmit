"""按已核实的网页文件路径填写多文件关卡；没有映射时保持单文件行为。"""
import hashlib
import json
from pathlib import Path

from .editor import MonacoEditor, normalize
from .workspace import select_file


def load_files(solution):
    solution = Path(solution).resolve()
    manifest = solution.with_suffix('.files.json')
    if not manifest.exists():
        return [(None, solution)]
    mapping = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError('多文件映射必须是非空对象。')
    files = []
    for remote, local in mapping.items():
        if not isinstance(remote, str) or not remote.strip() or not isinstance(local, str):
            raise ValueError('文件映射需要网页路径和本地相对路径。')
        path = (solution.parent / local).resolve()
        if not path.is_relative_to(solution.parent) or not path.is_file():
            raise ValueError('映射的本地文件缺失或超出作业目录。')
        files.append((remote, path))
    return files


def write_solution(page, solution, folder):
    files = load_files(solution)
    prepared = [(remote, path, normalize(path.read_text(encoding='utf-8-sig'))) for remote, path in files]
    if any(not code.strip() for _, _, code in prepared):
        raise ValueError('解答文件不能为空。')
    records = []
    for index, (remote, path, code) in enumerate(prepared):
        if remote is not None:
            select_file(page, remote)
        editor = MonacoEditor(page)
        (folder / f'file-{index}-before.txt').write_text(editor.read_code(), encoding='utf-8')
        (folder / f'file-{index}-local.txt').write_text(code, encoding='utf-8')
        editor.set_code(code)
        records.append({'remote': remote, 'local': str(path), 'sha256': hashlib.sha256(code.encode()).hexdigest()})
    (folder / 'files.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    return records
