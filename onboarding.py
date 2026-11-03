"""首次启动向导：加密保存模型密钥，从用户打开的页面取得课程地址。"""
import logging
import os
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yaml
from playwright.sync_api import sync_playwright

from ai.credentials import configure_api_key, get_api_key
from browser.navigation import navigate
from browser.session import browser_session, save_state
from configuration import load_settings, require_course


def initialize_config(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    template = Path(__file__).with_name("config.example.yaml").read_text(encoding="utf-8")
    with path.open("x", encoding="utf-8") as stream:
        stream.write(template)


def course_from_url(url: str) -> str | None:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "www.educoder.net"
            or not re.fullmatch(r"/classrooms/[A-Za-z0-9_-]+/shixun_homework/?", parsed.path)):
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def save_config(config_path, **changes):
    data = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    data.update(changes)
    temporary = config_path.with_suffix('.tmp')
    temporary.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')
    temporary.replace(config_path)


def ensure_browser(settings, config_path):
    """Windows 优先使用已安装 Chrome/Edge，缺少浏览器时安装 Playwright Chromium。"""
    if os.name != 'nt':
        return settings
    locations = {'chrome': 'Google/Chrome/Application/chrome.exe',
                 'msedge': 'Microsoft/Edge/Application/msedge.exe'}
    installed = {channel for channel, suffix in locations.items()
                 if any((Path(os.environ[var]) / suffix).is_file()
                        for var in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA') if os.environ.get(var))}
    if settings.browser_channel in installed:
        return settings
    if settings.browser_channel != 'chromium' and installed:
        channel = 'chrome' if 'chrome' in installed else 'msedge'
    else:
        with sync_playwright() as playwright:
            present = Path(playwright.chromium.executable_path).is_file()
        if not present:
            print('未找到可用浏览器，正在安装 Playwright Chromium（需要联网下载）……')
            try:
                subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], check=True)
            except subprocess.CalledProcessError:
                raise RuntimeError('Chromium 安装失败，请检查网络后重新运行 START.cmd。') from None
        channel = 'chromium'
    save_config(config_path, browser_channel=channel)
    logging.info('已选择可用浏览器：%s', channel)
    return replace(settings, browser_channel=channel)


def capture_course(settings, config_path):
    with browser_session(settings, interactive=True) as (context, page):
        navigate(page, "https://www.educoder.net/", settings)
        print("请在打开的浏览器中登录，并进入要处理的课程 → 实训作业页面。")
        print("之后会自动读取该课程全部分页。验证码或访问验证请在浏览器完成。")
        while True:
            answer = input("页面已打开后按回车开始；输入 q 取消：").strip().lower()
            if answer == "q":
                raise RuntimeError("已取消课程设置。")
            courses = {url for tab in context.pages if (url := course_from_url(tab.url))}
            if len(courses) != 1:
                print("请只保留一个目标课程的实训作业页面，然后按回车。")
                continue
            selected = next(iter(courses))
            # 先保存会话；失败时不把课程设置误报为完成。
            save_state(context, settings.session_file)
            save_config(config_path, course_url=selected)
            logging.info("已选择课程：%s", selected)
            return load_settings(config_path)


def prepare_start(config_path, *, reset_key=False):
    initialize_config(config_path)
    settings = load_settings(config_path)
    if settings.ai.enabled and (reset_key or not get_api_key(settings.root)):
        print("自动解题会将题目正文、可见代码模板发送给 DeepSeek，并消耗你的 API 额度。")
        configure_api_key(settings.root)
    settings = ensure_browser(settings, config_path)
    try:
        require_course(settings)
    except ValueError:
        settings = capture_course(settings, config_path)
    return settings
