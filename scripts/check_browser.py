"""实际浏览器诊断：只访问公开首页，不登录、不点击、不提交。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from browser.session import browser_session
from browser.navigation import navigate
from configuration import load_settings
from diagnostics import configure_logging, snapshot


def main():
    settings = load_settings(Path(__file__).resolve().parents[1] / "config.yaml")
    configure_logging(settings.root, settings.debug)
    with browser_session(settings, fresh=True, interactive=True) as (_, page):
        navigate(page, "https://www.educoder.net/", settings)
        # 给公开 SPA 有限的渲染时间；不用于判定登录成功。
        page.wait_for_timeout(5000)
        print("标题：", page.title())
        print("实际 DOM 中的链接/按钮（前 40 个）：")
        print(page.locator("a, button").evaluate_all("els => els.map(e => ({text: (e.innerText || '').trim(), href: e.getAttribute('href')})).filter(e => e.text).slice(0, 40)"))
        snapshot(page, settings.root, "public-home-smoke")
        (settings.root / "debug" / "public-home.html").write_text(page.content(), encoding="utf-8")


if __name__ == "__main__":
    main()
