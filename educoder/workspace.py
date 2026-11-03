"""Read the observed EduCoder Monaco workspace through its normal file menu.

The selectors below come from saved task DOM and the guided task runner.  This
module does not open answer panels, inspect private APIs, or change code.
"""
import re
import time
from pathlib import PurePosixPath
from weakref import WeakKeyDictionary

from .editor import MonacoEditor


_MENU = '[id^="env_"] .ant-dropdown-trigger'
_EDITOR = '.monaco-editor[role="code"]:visible'
_MAX_FILES = 20
_MODEL_CHANGE_TIMEOUT_MS = 15000
_SOURCE_SUFFIXES = {'.c', '.cc', '.cpp', '.cxx', '.h', '.hh', '.hpp', '.hxx'}
_selected = WeakKeyDictionary()


def _path(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError('网页文件路径为空或格式不明确。')
    parts = value.split('/')
    if (len(value) > 1024 or any(ord(c) < 32 for c in value)
            or '\\' in value or ':' in value or value.startswith('/')
            or any(part in ('', '.', '..') for part in parts)):
        raise ValueError('网页文件路径不是安全的相对路径。')
    if PurePosixPath(value).suffix.lower() not in _SOURCE_SUFFIXES:
        raise ValueError('当前仅支持 C/C++ 源文件与头文件。')
    return value


def _menu_items(page):
    page.bring_to_front()
    page.mouse.move(0, 0)
    page.wait_for_timeout(250)
    trigger = page.locator(_MENU)
    if trigger.count() != 1 or not trigger.is_visible():
        raise ValueError('未找到唯一代码文件菜单，无法确认文件路径。')
    trigger.hover()
    items = page.get_by_role('menuitem').filter(visible=True)
    items.first.wait_for(state='visible')
    count = items.count()
    if count < 1 or count > _MAX_FILES:
        raise ValueError('代码文件菜单为空或超过 20 个文件，停止自动读取。')
    paths = [_path(text.strip()) for text in items.all_inner_texts()]
    if len(paths) != len(set(paths)):
        raise ValueError('代码菜单包含重复文件路径。')
    return items, paths


def _uri(page):
    root = page.locator(_EDITOR)
    root.wait_for(state='visible', timeout=60000)
    if root.count() != 1:
        raise ValueError('工作区不是唯一可见的 Monaco 编辑器。')
    uri = root.get_attribute('data-uri')
    if not uri:
        raise ValueError('编辑器没有模型标识，无法确认文件已加载。')
    return uri


def _choose_from_open_menu(page, path, paths, *, require_change):
    if path not in paths:
        raise ValueError('目标文件不在当前网页代码菜单中。')
    item = page.get_by_role('menuitem', name=path, exact=True).filter(visible=True)
    if item.count() != 1 or not item.is_enabled():
        raise ValueError('目标文件不可选择或存在歧义。')
    before = _uri(page)
    _selected.pop(page, None)
    item.click()
    if require_change:
        try:
            page.wait_for_function('''([selector, before]) => {
                const nodes = [...document.querySelectorAll(selector.replace(':visible', ''))]
                    .filter(e => e.getClientRects().length);
                return nodes.length === 1 && nodes[0].getAttribute('data-uri')
                    && nodes[0].getAttribute('data-uri') !== before;
            }''', arg=[_EDITOR, before], timeout=_MODEL_CHANGE_TIMEOUT_MS)
        except Exception as exc:
            raise ValueError('切换文件后编辑器模型未更新，无法确认目标文件；请检查工作区 DOM。') from exc
    # Observe model stability, including delayed initial render.  Do not accept
    # a single frame or treat an arbitrary sleep as confirmation on its own.
    deadline = time.monotonic() + 15
    last = None
    stable_since = time.monotonic()
    while time.monotonic() < deadline:
        current = _uri(page)
        if current != last:
            last, stable_since = current, time.monotonic()
        if time.monotonic() - stable_since >= 0.7:
            _selected[page] = (page.url, path, current)
            return current
        page.wait_for_timeout(150)
    raise ValueError('编辑器模型持续变化，停止读取代码。')


def select_file(page, path):
    """Bind a path only after a verified model switch (or a sole-file menu).

    On a fresh multi-file workspace the existing model has no known filename.
    First select a different observed file and require a URI transition, then
    select the requested file and require another transition. If the probe was
    already open, its unchanged URI cannot prove its name: stop rather than
    treating a stable old model as a successful selection.
    """
    path = _path(path)
    _, paths = _menu_items(page)
    if path not in paths:
        raise ValueError('目标文件不在当前网页代码菜单中。')
    current_uri = _uri(page)
    previous = _selected.get(page)
    if previous and (previous[0] != page.url or previous[2] != current_uri):
        # Navigation or a manual tab switch invalidates the cached identity.
        _selected.pop(page, None)
        previous = None
    if previous is None and len(paths) > 1:
        probe = next(candidate for candidate in reversed(paths) if candidate != path)
        _choose_from_open_menu(page, probe, paths, require_change=True)
        _, paths = _menu_items(page)
        return _choose_from_open_menu(page, path, paths, require_change=True)
    return _choose_from_open_menu(page, path, paths,
                                  require_change=bool(previous and previous[1] != path))


def _heading(page, current):
    title = current.get('name', current.get('title'))
    number = current.get('number')
    if type(number) is not int or number < 1 or not isinstance(title, str) or not title.strip():
        raise ValueError('当前关卡信息不完整。')
    heading = page.locator('h3').filter(has_text=re.compile(r'^第\s*\d+\s*关[：:]'))
    if heading.count() != 1:
        raise ValueError('没有找到唯一当前关卡标题。')
    match = re.fullmatch(r'第\s*(\d+)\s*关[：:]\s*(.+)', heading.inner_text().strip())
    if not match or int(match[1]) != number or match[2].strip() != title:
        raise ValueError('读取期间当前关卡发生变化，停止生成解答。')
    return title


def _read_file(page):
    editor = MonacoEditor(page)
    editable = editor.input.is_editable()
    # aria-readonly is Monaco's accessible DOM indication. Absence alone is not
    # permission: Playwright's native editable check must also succeed.
    if editor.input.get_attribute('aria-readonly') == 'true' or editor.root.get_attribute('aria-readonly') == 'true':
        editable = False
    first = editor.read_code()
    page.wait_for_timeout(150)
    second = editor.read_code()
    editor.check()
    if first != second:
        raise ValueError('编辑器内容尚未稳定，停止读取题目。')
    return second, editable


def read_problem(page, *, assignment, current, max_chars=160000):
    """Return just the visible problem and observed files, never browser state."""
    if type(max_chars) is not int or max_chars <= 0:
        raise ValueError('题目读取长度限制必须是正整数。')
    title = _heading(page, current)
    original_url = page.url
    markdown = page.locator('.markdown-body:visible')
    if markdown.count() != 1:
        raise ValueError('没有找到唯一可见题目说明，停止自动生成。')
    description = markdown.inner_text().strip()
    if not description:
        raise ValueError('题目说明为空。')
    total = len(description) + len(title) + len(assignment)
    if total > max_chars:
        raise ValueError('题目超出 AI 上下文长度限制；未截断或发送题目。')
    _, paths = _menu_items(page)
    files = []
    for path in paths:
        _heading(page, current)
        if page.url != original_url:
            raise ValueError('读取期间页面地址发生变化。')
        select_file(page, path)
        code, editable = _read_file(page)
        total += len(path) + len(code)
        if total > max_chars:
            raise ValueError('代码模板超出 AI 上下文长度限制；未截断或发送题目。')
        files.append({'path': path, 'code': code, 'editable': editable})
    _heading(page, current)
    if page.url != original_url or markdown.inner_text().strip() != description:
        raise ValueError('读取期间题目内容发生变化。')
    if not any(file['editable'] for file in files):
        raise ValueError('没有发现可编辑代码文件。')
    # Re-check the file set in case a lazy menu changed while visiting files.
    _, final_paths = _menu_items(page)
    page.mouse.move(0, 0)
    if final_paths != paths:
        raise ValueError('读取期间代码文件列表发生变化。')
    return {'assignment': assignment, 'title': title, 'number': current['number'],
            'description': description, 'files': files}
