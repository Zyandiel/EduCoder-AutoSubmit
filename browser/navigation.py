import logging

from diagnostics import safe_url, snapshot


def navigate(page, url, settings):
    logging.info("打开页面：%s", safe_url(url))
    try:
        response = page.goto(url, wait_until="domcontentloaded")
        if response and response.status >= 400:
            raise RuntimeError(f"页面返回 HTTP {response.status}。")
        # SPA 可能持续发起网络请求，不使用 networkidle 判断登录或加载完成。
        logging.info("当前 URL：%s", safe_url(page.url))
        if settings.debug:
            snapshot(page, settings.root, "navigation")
    except Exception:
        snapshot(page, settings.root, "navigation-error")
        raise
