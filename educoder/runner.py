"""本地解答 -> 当前未完成关卡 -> 回读校验 -> 单次评测。最终提交未开放。"""
import hashlib
import json
import logging
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

import yaml
from browser.session import browser_session
from diagnostics import snapshot, safe_url
from educoder.challenges import inspect_assignment, move_to_pending
from educoder.editor import MonacoEditor, normalize
from educoder.evaluator import evaluate_once
from educoder.solution_files import write_solution


def selected_assignments(config_path, requested):
    if requested:
        return [requested]
    raw = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    entries = raw.get('assignments', [])
    if not isinstance(entries, list):
        raise ValueError('assignments 必须是列表。')
    result = []
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get('name'), str) or type(item.get('enabled', False)) is not bool:
            raise ValueError('assignments 项需要 name 字符串和 enabled 布尔值。')
        if item.get('enabled', False) and item['name'] not in result:
            result.append(item['name'])
    if not result:
        raise ValueError('没有启用的作业。')
    return result


def run_assignments(settings, names):
    run_dir = settings.root / 'logs' / datetime.now().strftime('run-%Y%m%d-%H%M%S-%f')
    run_dir.mkdir(parents=True)
    report = {'dry_run': True, 'final_submission': False, 'items': []}
    def persist():
        (run_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    persist()
    errors = False
    for name in names:
        # 没有本地代码就不启动该作业的学习环境。
        directory = (settings.solutions_dir / name).resolve()
        if not directory.is_relative_to(settings.solutions_dir.resolve()):
            raise ValueError('作业名称超出 solutions 目录。')
        if not directory.is_dir() or not any(directory.glob('*.cpp')):
            report['items'].append({'assignment': name, 'status': 'missing_solution'})
            logging.warning('%s：没有本地 cpp 文件，跳过。', name)
            errors = True
            persist()
            continue
        visited = set()
        for attempt in range(100):
            item = {'assignment': name, 'status': 'opening'}
            report['items'].append(item)
            persist()
            with ExitStack() as stack:
                page = None
                try:
                    context, page = stack.enter_context(browser_session(settings))
                    # 先检查详情，不进入已经全部完成的实训。
                    info = inspect_assignment(context, page, settings, name)
                    pending = [c for c in info['challenges'] if c['passed'] is not True]
                    if not pending:
                        item['status'] = 'already_completed'
                        persist()
                        break
                    if not any((directory / f'{c["number"]}.cpp').is_file() for c in pending):
                        item['status'] = 'missing_solution'
                        item['missing_files'] = [str(directory / f'{c["number"]}.cpp') for c in pending]
                        logging.warning('未完成关卡缺少本地代码：%s；不进入工作区。', ', '.join(item['missing_files']))
                        errors = True
                        persist()
                        break
                    info = inspect_assignment(context, page, settings, name, enter=True)
                    current = info['current']
                    page = next(p for p in context.pages if p.url == current['url'])
                    current = move_to_pending(page, info, directory)
                    page.locator('.monaco-editor[role="code"]:visible').wait_for(timeout=settings.navigation_timeout_ms)
                    item.update(current)
                    number = current['number']
                    if number in visited or current['passed'] is not False:
                        item['status'] = 'stopped_unverified_or_completed_current'
                        logging.warning('当前关卡重复、已完成或状态未知；不重复评测。')
                        errors = True
                        persist()
                        break
                    visited.add(number)
                    solution = Path(current['solution_path'])
                    if not solution.is_file():
                        item['status'] = 'missing_solution'
                        logging.warning('缺少 %s，停止此作业并继续其他作业。', solution)
                        errors = True
                        persist()
                        break
                    code = normalize(solution.read_text(encoding='utf-8-sig'))
                    if not code.strip():
                        raise ValueError('本地代码为空。')
                    folder = run_dir / str(len(report['items']))
                    folder.mkdir()
                    item['artifacts'] = str(folder)
                    item['sha256'] = hashlib.sha256(code.encode('utf-8')).hexdigest()
                    (folder / 'local.cpp').write_text(code, encoding='utf-8')
                    editor = MonacoEditor(page)
                    (folder / 'before.cpp').write_text(editor.read_code(), encoding='utf-8')
                    item['files'] = write_solution(page, solution, folder)
                    item['status'] = 'write_verified'
                    persist()
                    if settings.debug:
                        snapshot(page, settings.root, 'code-write-verified')
                    item['status'] = 'evaluation_started'
                    persist()  # 即使进程退出，也保留尚未确认的评测记录。
                    result = evaluate_once(page)
                    item['evaluation'] = result
                    item['status'] = result['status']
                    (folder / 'result.txt').write_text(page.locator('body').inner_text(), encoding='utf-8')
                    snapshot(page, settings.root, 'evaluation-' + result['status'])
                    persist()
                    logging.info('%s 第%s关：%s', name, number, result['text'])
                    if result['status'] != 'passed':
                        errors = True
                        break
                    # 通过后重新读详情，由网站继续挑战决定下一关，不猜测任务链接。
                except Exception as exc:
                    errors = True
                    if page and page.context.pages:
                        page = page.context.pages[-1]
                    item['status'] = 'error'
                    item['error'] = f'{type(exc).__name__}: {str(exc) if isinstance(exc, ValueError) else "浏览器或网络操作失败，见截图；不自动重试评测"}'
                    item['url'] = safe_url(page.url) if page else None
                    if page:
                        snapshot(page, settings.root, 'run-error')
                    try:
                        (run_dir / f'error-{len(report["items"])}.txt').write_text(page.locator('body').inner_text(timeout=5000), encoding='utf-8')
                    except Exception:
                        pass
                    logging.error('%s：%s', name, item['error'])
                    persist()
                    break
        else:
            errors = True
            logging.error('%s 已达到关卡上限。', name)
    logging.info('运行记录：%s；未执行最终提交。', run_dir)
    return 3 if errors else 0
