"""一键流程：检查本地文件、恢复登录、刷新列表、处理配置中的未完成作业。"""
import json
import logging
import os
from contextlib import contextmanager

import yaml

from playwright.sync_api import Error as PlaywrightError
from browser.session import browser_session, login
from educoder.assignments import list_assignments
from educoder.runner import run_assignments, selected_assignments
from educoder.solution_files import load_files
from ai.credentials import get_api_key


@contextmanager
def single_run(root):
    path = root / 'logs' / 'auto.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('已有一键任务在运行，请勿重复启动。') from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def check_local(settings, names):
    count = 0
    for name in names:
        directory = (settings.solutions_dir / name).resolve()
        if not directory.is_relative_to(settings.solutions_dir.resolve()):
            raise ValueError('作业名称超出 solutions 目录。')
        files = [p for p in directory.glob('*.cpp') if p.stem.isdigit()]
        if not files:
            logging.warning('%s：尚无本地解答，运行时会跳过。', name)
        for source in files:
            for _, path in load_files(source):
                if not path.read_text(encoding='utf-8-sig').strip():
                    raise ValueError(f'解答文件为空：{path}')
            count += 1
    logging.info('本地检查完成：%s 个启用实训，%s 份关卡解答。', len(names), count)
    return count


def choose_assignments(settings, config_path, assignments, requested=None):
    """保留真实详情 URL，避免两个同名实训互相覆盖。"""
    raw = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    entries = raw.get('assignments', [])
    if not isinstance(entries, list):
        raise ValueError('assignments 必须是列表。')
    enabled, disabled = set(), set()
    for item in entries:
        if (not isinstance(item, dict) or not isinstance(item.get('name'), str)
                or not item['name'].strip() or type(item.get('enabled', False)) is not bool):
            raise ValueError('assignments 项需要非空 name 和 enabled 布尔值。')
        (enabled if item.get('enabled', False) else disabled).add(item['name'])
    if enabled & disabled:
        raise ValueError('同一作业名称不能同时启用和禁用。')
    selected = {requested} if requested else enabled if settings.assignment_scope == 'configured' else None
    names = {a['name'] for a in assignments}
    missing = sorted(selected - names) if selected is not None else []
    wanted = [a for a in assignments if (selected is None and a['name'] not in disabled)
              or (selected is not None and a['name'] in selected)]
    return wanted, missing


def automatic(settings, config_path, *, check_only=False, requested=None):
    if not settings.dry_run:
        raise ValueError('一键模式暂只支持 dry_run: true，不执行最终提交。')
    choose_assignments(settings, config_path, [], requested)  # 在打开浏览器前验证过滤配置。
    if not settings.ai.enabled:
        names = [requested] if requested else selected_assignments(config_path, None)
        check_local(settings, names)
    if check_only:
        if settings.ai.enabled:
            if not get_api_key(settings.root):
                raise ValueError('尚未设置 DeepSeek API Key，请双击 START.cmd 或运行 main.py setup。')
            logging.info('AI 配置及密钥读取正常；无需本地 CPP。未调用 API，未验证余额或密钥有效性。')
        return 0
    with single_run(settings.root):
        if not settings.session_file.exists():
            print('首次运行：请在打开的浏览器中手动登录，按终端提示保存。')
            login(settings)
            if not settings.session_file.exists():
                raise RuntimeError('未保存会话，已取消自动运行。')
        def scan():
            with browser_session(settings, interactive=True) as (_, page):
                return list_assignments(page, settings)
        try:
            result = scan()
        except (PlaywrightError, ValueError, RuntimeError):
            logging.warning('无法读取课程。可能是登录失效、网络异常或页面变化。')
            answer = input('需要重新手动登录请输入 login；其他输入结束：').strip().lower()
            if answer != 'login':
                return 3
            login(settings, fresh=True)
            result = scan()  # 只在用户重新登录后再读取一次，不循环重试。
        if result:
            logging.error('列表读取不完整，停止自动填写，请查看 logs 和截图。')
            return result
        data = json.loads((settings.root / 'logs/assignments.json').read_text(encoding='utf-8'))
        if data.get('scan_complete') is not True or data.get('course_url') != settings.course_url:
            raise ValueError('列表读取不完整或属于其他课程，停止运行。')
        chosen, missing = choose_assignments(settings, config_path, data['assignments'], requested)
        if not settings.ai.enabled and not requested:
            chosen = [a for a in chosen if a['name'] in names]
        pending = [a for a in chosen if a['completed'] is not True and a.get('submission_window_open') is not False]
        completed = [a for a in chosen if a['completed'] is True]
        closed = [a for a in chosen if a['completed'] is not True and a.get('submission_window_open') is False]
        summary = {'dry_run': True, 'final_submission': False, 'completed_skipped': completed,
                   'pending': pending, 'missing_assignments': missing, 'closed_skipped': closed,
                   'mode': 'ai' if settings.ai.enabled else 'local'}
        for name in missing:
            logging.warning('课程中没有找到配置作业：%s', name)
        for assignment in closed:
            logging.warning('跳过已截止/归档实训：%s', assignment['name'])
        logging.info('跳过 %s 个已完成实训，开始处理 %s 个未完成实训。', len(completed), len(pending))
        result = run_assignments(settings, pending) if pending else 0
        result = result or (3 if missing or closed else 0)
        summary['exit_code'] = result
        (settings.root / 'logs/auto-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        logging.info('一键流程结束，结果见 logs/auto-summary.json。未执行最终提交。')
        return result
