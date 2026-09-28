"""根据 2026-09-11 实际课程 DOM 读取列表；不调用站点私有接口。"""
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from browser.navigation import navigate
from diagnostics import snapshot

# 已观察到的 CSS module 名称前缀，避免绑定随构建变化的 hash。
CARD = 'div[class^="listItem___"]'
NAME = 'span[class^="name___"]'
NEXT = 'li.ant-pagination-next'


@dataclass
class Assignment:
    name: str
    progress: str
    completed: bool | None
    status: str
    submission_window_open: bool | None
    can_submit: bool | None = None
    url: str | None = None
    error: str | None = None


def parse_card(data: dict) -> Assignment:
    name = data["name"].strip()
    if not name:
        raise ValueError("作业卡片缺少名称，页面 DOM 可能已变化。")
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", data.get("progress", ""))
    progress, completed = "未知", None
    if match:
        done, total = map(int, match.groups())
        if total > 0 and done <= total:
            progress, completed = f"{done}/{total}", done == total
    status = data.get("status", "").strip() or "未知"
    # 开放期不等于已通过评测或可以最终提交。
    window = True if status in {"提交中", "补交中"} else False if status in {"已截止", "已归档"} else None
    return Assignment(name, progress, completed, status, window)


def wait_for_cards(page, settings):
    try:
        page.locator(f"{CARD} {NAME}").first.wait_for(state="visible", timeout=settings.navigation_timeout_ms)
    except PlaywrightError as exc:
        snapshot(page, settings.root, "assignment-list-missing")
        raise RuntimeError("未找到已验证的作业列表 DOM：可能登录失效、课程无权限、列表为空或 DOM 改版。请运行 inspect --html 检查；不会当作零项成功。") from exc


def read_cards(page):
    data = page.locator(CARD).evaluate_all("""cards => cards.map(card => ({
        name: card.querySelector('span[class^="name___"]')?.textContent || '',
        status: card.querySelector('.tag-style')?.textContent || '',
        progress: card.querySelector('i.icon-wanchengjindu')?.parentElement?.textContent || ''
    }))""")
    return [parse_card(item) for item in data]


def resolve_link(page, card, settings):
    """实测标题打开新标签页；不点击开始学习或提交总结。"""
    previous_pages = set(page.context.pages)
    try:
        with page.expect_popup(timeout=settings.action_timeout_ms) as event:
            card.locator(NAME).click()
        popup = event.value
        course_path = urlsplit(settings.course_url).path.rstrip("/")
        # 实际站点先创建空标签页，再异步设置地址，不能把初始 about:blank 当成失败。
        popup.wait_for_url(
            re.compile(r"^https://www\.educoder\.net" + re.escape(course_path) + r"/\d+/detail(?:[?#]|$)"),
            wait_until="domcontentloaded", timeout=settings.navigation_timeout_ms,
        )
        actual = urlsplit(popup.url)
        if actual.scheme != "https" or actual.hostname != "www.educoder.net" or not re.fullmatch(re.escape(course_path) + r"/\d+/detail", actual.path):
            raise RuntimeError("标题打开的地址不是已验证的本课程作业详情地址，可能需要重新登录。")
        return popup.url
    finally:
        for tab in list(page.context.pages):
            if tab not in previous_pages:
                tab.close()


def collect_assignments(page, settings):
    navigate(page, settings.course_url, settings)
    wait_for_cards(page, settings)
    results = []
    signatures = set()
    for number in range(1, 101):
        batch = read_cards(page)
        signature = tuple((item.name, item.progress, item.status) for item in batch)
        if not batch or signature in signatures:
            raise RuntimeError("分页结果为空或重复；停止读取，避免无限请求。")
        signatures.add(signature)
        logging.info("第 %s 页：%s 个实训。", number, len(batch))
        if settings.debug:
            snapshot(page, settings.root, f"assignment-list-{number}")
        for index, item in enumerate(batch):
            logging.info("读取作业详情地址：%s（%s，%s）", item.name, item.progress, item.status)
            original_url = page.url
            try:
                item.url = resolve_link(page, page.locator(CARD).nth(index), settings)
            except (PlaywrightError, RuntimeError) as exc:
                item.error = f"作业链接读取失败（{type(exc).__name__}），请检查截图和页面 DOM。"
                logging.warning("%s：%s", item.name, item.error)
                snapshot(page, settings.root, f"assignment-link-error-{number}-{index + 1}")
                if page.url != original_url:
                    raise RuntimeError("标题导航行为已变化，停止列表读取以免匹配错误作业。") from exc
            results.append(item)
            page.wait_for_timeout(700)
        following = page.locator(NEXT)
        if following.count() != 1:
            raise RuntimeError("未找到唯一分页控件，无法确认已经读取全部作业。")
        if following.get_attribute("aria-disabled") == "true":
            return results
        before = page.locator(CARD).all_text_contents()
        following.click()
        try:
            page.wait_for_function(
                "args => JSON.stringify(Array.from(document.querySelectorAll(args.selector), e => e.textContent)) !== JSON.stringify(args.before)",
                arg={"selector": CARD, "before": before}, timeout=settings.navigation_timeout_ms,
            )
            wait_for_cards(page, settings)
        except PlaywrightError as exc:
            snapshot(page, settings.root, "pagination-timeout")
            raise RuntimeError("翻页超时，无法确认列表完整。") from exc
    raise RuntimeError("已达到 100 页上限，未将不完整列表标记为成功。")


def list_assignments(page, settings):
    assignments = collect_assignments(page, settings)
    complete = all(item.error is None for item in assignments)
    report = settings.root / "logs" / "assignments.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    temporary = report.with_suffix(".tmp")
    temporary.write_text(json.dumps({
        "captured_at": datetime.now().astimezone().isoformat(),
        "course_url": settings.course_url, "scan_complete": complete,
        "note": "completed 仅表示关卡进度；can_submit 未确认，禁止据此最终提交。",
        "assignments": [asdict(item) for item in assignments],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(report)
    for item in assignments:
        state = "已完成关卡" if item.completed is True else "未完成关卡" if item.completed is False else "进度未知"
        print(f"{item.name} | {item.progress} | {state} | {item.status} | 最终可提交：未确认")
        print(f"  {item.url or item.error}")
    logging.info("读取 %s 个实训，结果保存至 %s", len(assignments), report)
    return 0 if complete else 3
