"""仅模拟浏览器正常操作；登录、验证码和授权均由用户完成。"""
import json
import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

from diagnostics import snapshot
from .navigation import navigate


def read_state(path: Path):
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ValueError("会话文件不可读或损坏；请使用 login --fresh 重新登录。") from exc
    if not isinstance(state, dict) or not isinstance(state.get("cookies"), list) or not isinstance(state.get("origins"), list):
        raise ValueError("会话文件格式无效；请使用 login --fresh 重新登录。")
    return state


def save_state(context, path: Path):
    """同目录临时文件 + 原子替换，保存失败时保留旧会话。"""
    state = context.storage_state(indexed_db=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".session-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    logging.info("会话已保存：%s（含登录凭据，请勿分享）", path)


@contextmanager
def browser_session(settings, *, fresh=False, interactive=False):
    state = None if fresh else read_state(settings.session_file)
    logging.info("%s", "恢复已保存会话（有效性需在网页确认）。" if state is not None else "启动新会话。")
    with sync_playwright() as playwright:
        logging.info("浏览器通道：%s", settings.browser_channel)
        browser = playwright.chromium.launch(
            channel=None if settings.browser_channel == "chromium" else settings.browser_channel,
            headless=False if interactive or settings.debug else settings.headless,
        )
        try:
            context = browser.new_context(storage_state=state, viewport={"width": 1440, "height": 960})
            context.set_default_navigation_timeout(settings.navigation_timeout_ms)
            context.set_default_timeout(settings.action_timeout_ms)
            page = context.new_page()
            try:
                yield context, page
            finally:
                context.close()
        finally:
            browser.close()


def login(settings, *, fresh=False):
    with browser_session(settings, fresh=fresh, interactive=True) as (context, page):
        navigate(page, "https://www.educoder.net/", settings)
        print("\n请在浏览器中手动登录，并完成网站要求的验证码/验证。")
        print("确认已显示你的登录身份后，回到本窗口输入 save 保存。输入 q 退出且不保存。")
        print("目前尚未取得已登录 DOM，因此不会自动判断登录成功或会话过期。")
        while True:
            answer = input("登录完成？[save/q] ").strip().lower()
            if answer == "q":
                logging.info("已取消；未修改原会话。")
                return
            if answer != "save":
                continue
            if not context.pages:
                raise RuntimeError("浏览器页面已关闭，请重新执行 login。")
            save_state(context, settings.session_file)
            if settings.debug:
                snapshot(context.pages[-1], settings.root, "session-saved")
            return
