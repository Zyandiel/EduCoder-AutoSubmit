"""Windows 入口：python main.py login。"""
import argparse
import logging
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError

from browser.navigation import navigate
from browser.session import browser_session, login, save_state
from configuration import default_config, load_settings, require_course
from diagnostics import configure_logging, snapshot
from educoder.assignments import list_assignments
from educoder.challenges import inspect_assignment
from educoder.runner import run_assignments, selected_assignments
from educoder.auto import automatic


def parser():
    result = argparse.ArgumentParser(description="EduCoder Helper：本地代码填写、回读校验与单次评测")
    result.add_argument("--config", type=Path, default=default_config(Path(__file__).resolve().parent), help="配置路径（默认优先 config.local.yaml，兼容 config.yaml）")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="从示例创建本地配置，不覆盖已有文件")
    auth = commands.add_parser("login", help="手动登录并保存会话")
    auth.add_argument("--fresh", action="store_true", help="忽略旧会话，重新手动登录")
    inspect = commands.add_parser("inspect", help="恢复会话，手动检查课程页面并保存截图")
    inspect.add_argument("--html", action="store_true", help="额外导出当前页面 HTML（分享前检查个人信息和凭据）")
    inspect.add_argument("--assignment", help="读取指定作业详情中的关卡")
    inspect.add_argument("--enter", action="store_true", help="进入实训识别当前关卡和编辑器，不写入或评测；须同时指定 --assignment")
    commands.add_parser("list", help="读取全部列表分页及实际作业详情链接，保存 logs/assignments.json")
    run = commands.add_parser("run", help="填写本地代码、完整回读校验并单次评测；最终提交暂未开放")
    run.add_argument("--assignment")
    run.add_argument("--dry-run", action="store_true")
    commands.add_parser("submit", help="保留入口：最终提交尚未开放，退出码 2")
    auto = commands.add_parser('auto', help='一键恢复登录、刷新列表、自动填写并评测本地解答')
    auto.add_argument('--check', action='store_true', help='只检查本地配置与解答，不打开网站')
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            target = args.config.resolve()
            if target.exists():
                print(f"配置已存在，保留原文件：{target}")
            else:
                template = Path(__file__).with_name("config.example.yaml").read_text(encoding="utf-8")
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("x", encoding="utf-8") as stream:
                    stream.write(template)
                print(f"已创建：{target}")
            print("填写 course_url、启用 assignments，并准备 solutions 中的本地代码后再运行。")
            return 0
        settings = load_settings(args.config)
        configure_logging(settings.root, settings.debug)
        logging.info("dry_run=%s, debug=%s", settings.dry_run or getattr(args, "dry_run", False), settings.debug)
        if args.command in ("list", "run", "inspect") or (args.command == "auto" and not args.check):
            require_course(settings)
        if args.command == 'auto':
            return automatic(settings, args.config, check_only=args.check)
        if args.command == 'run':
            if not (settings.dry_run or args.dry_run):
                raise ValueError('最终提交尚未实现，请使用 --dry-run 或保持 dry_run: true。')
            return run_assignments(settings, selected_assignments(args.config, args.assignment))
        if args.command == "submit":
            logging.error("%s 尚未实现：最终提交入口和条件尚未验证。未执行任何提交。", args.command)
            return 2
        if args.command == "login":
            login(settings, fresh=args.fresh)
        elif args.command == "list":
            if not settings.session_file.exists():
                raise ValueError("尚未保存登录状态，请先运行 login。")
            with browser_session(settings) as (_, page):
                return list_assignments(page, settings)
        elif args.command == "inspect":
            if args.enter and not args.assignment:
                raise ValueError('--enter 必须和 --assignment 一起使用。')
            if args.assignment:
                with browser_session(settings, interactive=True) as (context, page):
                    try:
                        inspect_assignment(context, page, settings, args.assignment, enter=args.enter, export_html=args.html)
                    except Exception:
                        if context.pages:
                            snapshot(context.pages[-1], settings.root, 'assignment-inspection-error')
                        raise
                return 0
            with browser_session(settings, interactive=True) as (context, page):
                navigate(page, settings.course_url, settings)
                print("请在浏览器确认课程页面。如登录失效，请手动登录再打开课程页面。")
                answer = input("页面加载完成后输入 capture 保存截图及会话；其他输入取消：").strip().lower()
                if answer == "capture":
                    if not context.pages:
                        raise RuntimeError("浏览器页面已关闭。")
                    snapshot(context.pages[-1], settings.root, "course-inspection")
                    if args.html:
                        target = settings.root / "debug" / "course.html"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(context.pages[-1].content(), encoding="utf-8")
                        logging.info("HTML 已导出：%s（分享前检查个人信息和凭据）", target)
                    save_state(context, settings.session_file)
        return 0
    except (KeyboardInterrupt, EOFError):
        logging.warning("操作取消；未执行任何提交。")
        return 130
    except PlaywrightError as exc:
        # Playwright 原始错误可能含 URL 查询参数，日志不直接写入。
        logging.error("浏览器操作失败（%s）。请检查网络、登录状态及 browser_channel 对应的浏览器是否已安装。", type(exc).__name__)
        return 1
    except (ValueError, OSError, RuntimeError) as exc:
        logging.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
