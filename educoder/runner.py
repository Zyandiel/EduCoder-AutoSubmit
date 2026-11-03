"""读取真实题目 -> AI 生成或本地解答 -> 回读校验 -> 单次评测。"""
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
from educoder.workspace import read_problem
from ai.client import DeepSeekClient, AIError
from ai.credentials import get_api_key


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


def save_generated(folder, answer):
    """模型只提供网页路径；本地文件名由程序生成，不能越界写文件。"""
    target = folder / 'generated'
    target.mkdir()
    mapping = {}
    for index, entry in enumerate(answer['files'], 1):
        filename = f'{index}.cpp'
        (target / filename).write_text(normalize(entry['code']), encoding='utf-8')
        mapping[entry['path']] = filename
    (target / '1.files.json').write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding='utf-8')
    return target / '1.cpp'


def run_assignments(settings, names):
    run_dir = settings.root / 'logs' / datetime.now().strftime('run-%Y%m%d-%H%M%S-%f')
    run_dir.mkdir(parents=True)
    report = {'dry_run': True, 'final_submission': False,
              'mode': 'ai' if settings.ai.enabled else 'local', 'items': []}
    def persist():
        (run_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    persist()
    errors = False
    client = None
    for target in names:
        name = target['name'] if isinstance(target, dict) else target
        detail_url = target.get('url') if isinstance(target, dict) else None
        # 没有本地代码就不启动该作业的学习环境。
        try:
            directory = run_dir / 'pending' if settings.ai.enabled else (settings.solutions_dir / name).resolve()
            if not settings.ai.enabled and not directory.is_relative_to(settings.solutions_dir.resolve()):
                raise ValueError('作业名称超出 solutions 目录。')
        except (ValueError, OSError):
            report['items'].append({'assignment': name, 'status': 'invalid_local_path'})
            logging.warning('%s：本地路径无效，跳过此实训。', name)
            errors = True
            persist()
            continue
        if not settings.ai.enabled and (not directory.is_dir() or not any(directory.glob('*.cpp'))):
            report['items'].append({'assignment': name, 'status': 'missing_solution'})
            logging.warning('%s：没有本地 cpp 文件，跳过。', name)
            errors = True
            persist()
            continue
        visited = set()
        for attempt in range(100):
            item = {'assignment': name, 'detail_url': detail_url, 'status': 'opening'}
            report['items'].append(item)
            persist()
            with ExitStack() as stack:
                page = None
                try:
                    context, page = stack.enter_context(browser_session(settings))
                    # 先检查详情，不进入已经全部完成的实训。
                    options = {'detail_url': detail_url} if detail_url else {}
                    info = inspect_assignment(context, page, settings, name, **options)
                    pending = [c for c in info['challenges'] if c['passed'] is not True]
                    if not pending:
                        item['status'] = 'already_completed'
                        persist()
                        break
                    if not settings.ai.enabled and not any((directory / f'{c["number"]}.cpp').is_file() for c in pending):
                        item['status'] = 'missing_solution'
                        item['missing_files'] = [str(directory / f'{c["number"]}.cpp') for c in pending]
                        logging.warning('未完成关卡缺少本地代码：%s；不进入工作区。', ', '.join(item['missing_files']))
                        errors = True
                        persist()
                        break
                    info = inspect_assignment(context, page, settings, name, enter=True, **options)
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
                    folder = run_dir / str(len(report['items']))
                    folder.mkdir()
                    item['artifacts'] = str(folder)
                    solution = Path(current['solution_path'])
                    if settings.ai.enabled:
                        if client is None:
                            key = get_api_key(settings.root)
                            if not key:
                                raise AIError('尚未设置 DeepSeek API Key，请运行 main.py setup。', fatal_run=True)
                            client = DeepSeekClient(settings.ai, key)
                        logging.info('%s 第%s关：读取题目正文和代码模板。', name, number)
                        problem = read_problem(page, assignment=name, current=current,
                                               max_chars=settings.ai.max_context_chars)
                        (folder / 'problem.json').write_text(json.dumps(problem, ensure_ascii=False, indent=2), encoding='utf-8')
                        item['status'] = 'generating'
                        persist()
                        logging.info('DeepSeek 正在生成解答（模型 %s）；本关只调用一次。', settings.ai.model)
                        answer = client.solve(problem)
                        (folder / 'answer.json').write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding='utf-8')
                        if answer['status'] != 'ready':
                            item['status'] = 'needs_context'
                            item['reason'] = answer.get('reason', '题目上下文不完整。')
                            logging.warning('%s 第%s关缺少必要上下文，记录后继续其他作业。', name, number)
                            errors = True
                            persist()
                            break
                        # API 等待期间用户可能切换关卡，不能将答案写进其他题。
                        if page.url != current['url']:
                            raise ValueError('生成期间工作区地址已变化，停止写入。')
                        fresh = read_problem(page, assignment=name, current=current,
                                             max_chars=settings.ai.max_context_chars)
                        if fresh != problem:
                            raise ValueError('生成期间题目或模板已变化，停止写入并保留生成结果。')
                        solution = save_generated(folder, answer)
                        item['generated_solution'] = str(solution)
                    if not solution.is_file():
                        item['status'] = 'missing_solution'
                        logging.warning('缺少 %s，停止此作业并继续其他作业。', solution)
                        errors = True
                        persist()
                        break
                    code = normalize(solution.read_text(encoding='utf-8-sig'))
                    if not code.strip():
                        raise ValueError('本地代码为空。')
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
                    item['error'] = f'{type(exc).__name__}: {str(exc) if isinstance(exc, (ValueError, AIError)) else "浏览器或网络操作失败，见截图；不自动重试评测"}'
                    item['url'] = safe_url(page.url) if page else None
                    if page:
                        snapshot(page, settings.root, 'run-error')
                    try:
                        (run_dir / f'error-{len(report["items"])}.txt').write_text(page.locator('body').inner_text(timeout=5000), encoding='utf-8')
                    except Exception:
                        pass
                    logging.error('%s：%s', name, item['error'])
                    persist()
                    if isinstance(exc, AIError) and exc.fatal_run:
                        logging.error('API 暂不可用或调用预算已用完，结束本轮以避免无效请求。')
                        return 3
                    break
        else:
            errors = True
            logging.error('%s 已达到关卡上限。', name)
    logging.info('运行记录：%s；未执行最终提交。', run_dir)
    return 3 if errors else 0
