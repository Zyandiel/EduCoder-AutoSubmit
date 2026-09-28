"""根据已观察到的作业详情表格和工作区标题识别关卡。"""
import json
import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from browser.navigation import navigate
from diagnostics import snapshot


@dataclass
class Challenge:
    number: int
    name: str
    status: str
    passed: bool | None


def parse_table(headers, rows):
    required = ('序号', '关卡名称', '通过状态')
    if any(headers.count(key) != 1 for key in required):
        raise ValueError('关卡表格列发生变化，停止识别。')
    indices = [headers.index(key) for key in required]
    result = []
    for row in rows:
        if len(row) != len(headers):
            raise ValueError('关卡表格行列不一致。')
        number, name, status = [row[index].strip() for index in indices]
        if not number.isdigit() or int(number) < 1 or not name:
            raise ValueError('关卡序号或名称无法识别。')
        passed = True if status == '已通过' else False if status in ('未评测', '未通过') else None
        result.append(Challenge(int(number), name, status, passed))
    if not result or [c.number for c in result] != list(range(1, len(result) + 1)):
        raise ValueError('关卡序号缺失、重复或不连续；无法安全匹配本地文件。')
    return result


def find_assignment(settings, name):
    path = settings.root / 'logs/assignments.json'
    if not path.exists():
        raise ValueError('请先运行 list 生成作业链接。')
    report = json.loads(path.read_text(encoding='utf-8'))
    if report.get('course_url') != settings.course_url or report.get('scan_complete') is not True:
        raise ValueError('列表属于其他课程或读取不完整，请重新运行 list。')
    matches = [a for a in report.get('assignments', []) if a.get('name') == name]
    if len(matches) != 1:
        raise ValueError('作业名称不存在或不唯一，请使用 list 中的完整名称。')
    url = matches[0].get('url')
    if not isinstance(url, str):
        raise ValueError('缺少详情地址，请重新运行 list。')
    parsed = urlsplit(url)
    base = urlsplit(settings.course_url)
    if parsed.scheme != 'https' or parsed.netloc != base.netloc or not re.fullmatch(re.escape(base.path.rstrip('/')) + r'/\d+/detail', parsed.path):
        raise ValueError('详情链接不是本课程的已验证地址。')
    return url


def parse_current(text, challenges):
    match = re.fullmatch(r'第\s*(\d+)\s*关[：:]\s*(.+)', text.strip())
    if not match:
        raise ValueError('工作区当前关卡标题无法识别。')
    matches = [c for c in challenges if c.number == int(match[1]) and c.name == match[2].strip()]
    if len(matches) != 1:
        raise ValueError('工作区关卡与作业详情不匹配，停止操作。')
    return matches[0]


def move_to_pending(page, info, directory):
    """只用实际上一关/下一关链接，回到最早未完成关卡。"""
    challenges = [Challenge(**c) for c in info['challenges']]
    pending = [c.number for c in challenges if c.passed is not True]
    if not pending:
        raise ValueError('没有需要处理的关卡。')
    target = min(pending)
    heading = page.locator('h3').filter(has_text=re.compile(r'^第\s*\d+\s*关[：:]'))
    for _ in range(len(challenges) + 1):
        heading.wait_for(state='visible')
        current = parse_current(heading.inner_text(), challenges)
        if current.number == target:
            if current.passed is not False:
                raise ValueError('关卡通过状态未知，停止填写。')
            solution = directory / f'{current.number}.cpp'
            return {**asdict(current), 'url': page.url, 'solution_path': str(solution)}
        step = 1 if current.number < target else -1
        if step == 1 and current.passed is not True:
            raise ValueError('不能越过尚未通过的关卡。')
        next_number = current.number + step
        popup = page.locator('footer a.current').filter(has_text=re.compile(r'^下一关$'))
        if step == 1 and popup.count() == 1 and popup.is_visible():
            popup.click()
        else:
            page.get_by_role('link', name='下一关' if step == 1 else '上一关', exact=True).click()
        page.locator('h3').filter(has_text=re.compile(r'^第\s*' + str(next_number) + r'\s*关[：:]')).wait_for(timeout=60000)
    raise ValueError('无法定位待处理关卡。')


def inspect_assignment(context, page, settings, name, *, enter=False, export_html=False):
    navigate(page, find_assignment(settings, name), settings)
    page.get_by_text(name, exact=True).first.wait_for(timeout=settings.navigation_timeout_ms)
    table = page.locator('table').filter(has=page.get_by_role('columnheader', name='关卡名称', exact=True))
    table.locator('tbody tr.ant-table-row').first.wait_for(timeout=settings.navigation_timeout_ms)
    if table.count() != 1:
        raise ValueError('未找到唯一关卡表格。')
    headers = table.locator('thead th').all_text_contents()
    rows = table.locator('tbody tr.ant-table-row').evaluate_all('rows => rows.map(r => Array.from(r.querySelectorAll("td"), c => c.innerText.trim()))')
    challenges = parse_table([h.strip() for h in headers], rows)
    result = {'assignment': name, 'detail_url': page.url, 'challenges': [asdict(c) for c in challenges], 'current': None}
    for c in challenges:
        print(f'第{c.number}关：{c.name} | {c.status}')
    if enter:
        # 两种入口文字均已在真实作业详情页观察到。
        button = page.get_by_text(re.compile(r'^(继续挑战|开启挑战)$'))
        button.first.wait_for(state='visible', timeout=settings.navigation_timeout_ms)
        if button.count() != 1 or not button.is_visible():
            raise ValueError('未找到唯一已验证的挑战入口，请提供该作业详情 DOM。')
        previous_pages = set(context.pages)
        button.click()
        task_pattern = re.compile(r'^https://www\.educoder\.net/tasks/')
        target = page
        # 实测在当前页导航；同时接收可能新增的标签页，不重复点击。
        try:
            page.wait_for_url(task_pattern, timeout=settings.action_timeout_ms)
        except PlaywrightTimeout:
            candidates = [p for p in context.pages if task_pattern.match(p.url) and (p == page or p not in previous_pages)]
            if len(candidates) != 1:
                raise ValueError('未进入唯一实训工作区，可能需要手动完成验证。')
            target = candidates[0]
        heading = target.locator('h3').filter(has_text=re.compile(r'^第\s*\d+\s*关[：:]'))
        heading.wait_for(timeout=settings.navigation_timeout_ms)
        current = parse_current(heading.inner_text(), challenges)
        editor = target.locator('.monaco-editor[role="code"]')
        editor.first.wait_for(timeout=settings.navigation_timeout_ms)
        if editor.count() != 1:
            raise ValueError('存在多个 Monaco 编辑器，不能确定目标。')
        # 只报告 DOM 类型；不把编辑器内部 textarea 当作代码写入接口。
        solution = (settings.solutions_dir / name / f'{current.number}.cpp').resolve()
        if not solution.is_relative_to(settings.solutions_dir.resolve()):
            raise ValueError('作业名称对应的本地路径超出了 solutions 目录。')
        result['current'] = {**asdict(current), 'url': target.url, 'editor': 'Monaco', 'solution_path': str(solution), 'solution_exists': solution.is_file()}
        print(f'当前第{current.number}关，编辑器：Monaco；本地文件：{solution}（{"存在" if solution.is_file() else "尚未提供"}）')
        page = target
    if settings.debug:
        snapshot(page, settings.root, 'assignment-inspection')
    if export_html:
        (settings.root / 'debug').mkdir(parents=True, exist_ok=True)
        (settings.root / 'debug/assignment-inspection.html').write_text(page.content(), encoding='utf-8')
    output = settings.root / 'logs/challenges.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result
