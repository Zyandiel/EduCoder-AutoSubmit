"""配置读取；相对路径以配置文件所在目录为基准。"""
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml


@dataclass(frozen=True)
class Settings:
    root: Path
    course_url: str
    solutions_dir: Path
    session_file: Path
    dry_run: bool
    debug: bool
    headless: bool
    browser_channel: str
    navigation_timeout_ms: int
    action_timeout_ms: int


def load_settings(path: Path) -> Settings:
    path = path.resolve()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError("YAML 格式错误，请检查缩进及冒号。") from exc
    if not isinstance(data, dict):
        raise ValueError("配置文件必须是 YAML 对象。")
    for key in ("dry_run", "debug", "headless"):
        if key in data and not isinstance(data[key], bool):
            raise ValueError(f"{key} 必须是 true 或 false，不能加引号。")
    channel = data.get("browser_channel", "chromium")
    if channel not in ("chromium", "chrome", "msedge"):
        raise ValueError("browser_channel 必须是 chromium、chrome 或 msedge。")
    url = data.get("course_url", "")
    if not isinstance(url, str):
        raise ValueError("course_url 必须是字符串。")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "www.educoder.net" or parsed.username or parsed.password:
        raise ValueError("course_url 必须是 https://www.educoder.net/ 下的地址。")
    for key in ("navigation_timeout_ms", "action_timeout_ms"):
        value = data.get(key, 60000 if key == "navigation_timeout_ms" else 15000)
        if type(value) is not int or value <= 0:
            raise ValueError(f"{key} 必须是正整数。")
    def local_path(key: str, default: str) -> Path:
        value = data.get(key, default)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} 必须是非空路径。")
        return (path.parent / value).resolve()
    return Settings(
        root=path.parent, course_url=url,
        solutions_dir=local_path("solutions_dir", "solutions"),
        session_file=local_path("session_file", ".auth/storage_state.json"),
        dry_run=data.get("dry_run", True), debug=data.get("debug", True),
        headless=data.get("headless", False),
        browser_channel=channel,
        navigation_timeout_ms=data.get("navigation_timeout_ms", 60000),
        action_timeout_ms=data.get("action_timeout_ms", 15000),
    )
