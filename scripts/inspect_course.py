"""开发诊断：只读打开配置课程，保存实际 DOM，不操作作业。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from browser.navigation import navigate
from browser.session import browser_session
from configuration import load_settings
from diagnostics import configure_logging, snapshot


def main():
    settings = load_settings(Path(__file__).resolve().parents[1] / "config.yaml")
    configure_logging(settings.root, settings.debug)
    with browser_session(settings, interactive=True) as (context, page):
        navigate(page, settings.course_url, settings)
        page.wait_for_timeout(7000)
        snapshot(page, settings.root, "course-dom-discovery")
        (settings.root / "debug" / "course.html").write_text(page.content(), encoding="utf-8")
        print(page.locator("body").inner_text()[:18000])
        print("LINKS", page.locator("a").evaluate_all("els => els.map(e => ({text: e.innerText.trim(), href: e.getAttribute('href')})).filter(e => e.text)"))
        if "--open-first" in sys.argv:
            page.locator('div[class^="listItem___"] span[class^="name___"]').first.click()
            page.wait_for_timeout(5000)
            print("TABS", [tab.url for tab in context.pages])
            page = context.pages[-1]
            print("DESTINATION", page.url)
            print(page.locator("body").inner_text()[:10000])
            snapshot(page, settings.root, "assignment-detail-discovery")
            (settings.root / "debug" / "assignment-detail.html").write_text(page.content(), encoding="utf-8")


if __name__ == "__main__":
    main()
