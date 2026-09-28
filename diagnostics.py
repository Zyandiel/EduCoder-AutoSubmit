import json
import logging
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def safe_url(url: str) -> str:
    """日志省略 query/fragment，避免记录认证重定向参数。"""
    value = urlsplit(url)
    return urlunsplit((value.scheme, value.netloc, value.path, "", ""))


def configure_logging(root: Path, debug: bool) -> None:
    directory = root / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(
            directory / f"{datetime.now():%Y-%m-%d}.log", encoding="utf-8")],
        force=True,
    )


def snapshot(page, root: Path, label: str) -> None:
    """诊断失败不能覆盖原来的异常。截图可能包含个人信息。"""
    directory = root / "debug" / "screenshots"
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.now():%Y%m%d-%H%M%S-%f}-{re.sub(r'[^a-zA-Z0-9_-]', '_', label)}"
    try:
        (directory / f"{stem}.json").write_text(json.dumps({
            "step": label, "url": safe_url(page.url), "title": page.title(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        page.screenshot(path=str(directory / f"{stem}.png"), full_page=True, timeout=10000)
    except Exception as exc:
        logging.warning("保存调试截图失败（%s）。", type(exc).__name__)
