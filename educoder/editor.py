"""按模型 URI 读取标准 Monaco API；未公开 API 时使用正常键盘和剪贴板。"""
import uuid
from contextlib import contextmanager
from urllib.parse import urlsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeout


def normalize(code):
    return code.replace('\r\n', '\n').replace('\r', '\n')


class MonacoEditor:
    def __init__(self, page):
        self.page = page
        self.root = page.locator('.monaco-editor[role="code"]:visible')
        if self.root.count() != 1:
            raise ValueError('需要唯一可见 Monaco 编辑器，不能确定目标。')
        self.input = self.root.locator('textarea.inputarea')
        if self.input.count() != 1:
            raise ValueError('Monaco 输入控件 DOM 已变化。')
        self.uri = self.root.get_attribute('data-uri')

    def check(self):
        if self.root.count() != 1 or self.root.get_attribute('data-uri') != self.uri:
            raise ValueError('编辑器模型已切换，停止写入。')

    @contextmanager
    def clipboard(self):
        origin = urlsplit(self.page.url)
        self.page.context.grant_permissions(['clipboard-read', 'clipboard-write'], origin=f'{origin.scheme}://{origin.netloc}')
        self.page.bring_to_front()
        old = self.page.evaluate('navigator.clipboard.readText()')
        try:
            yield
        finally:
            self.page.evaluate('text => navigator.clipboard.writeText(text)', old)

    def _read(self):
        self.check()
        marker = 'educoder-copy-' + uuid.uuid4().hex
        self.page.evaluate('text => navigator.clipboard.writeText(text)', marker)
        self.input.focus()
        self.page.keyboard.press('Control+a')
        self.page.keyboard.press('Control+c')
        try:
            self.page.wait_for_function('async marker => (await navigator.clipboard.readText()) !== marker', arg=marker, timeout=5000)
        except PlaywrightTimeout:
            raise ValueError('无法完整复制编辑器内容，可能是空模板或复制失败；未将读取失败当作空文件。') from None
        return normalize(self.page.evaluate('navigator.clipboard.readText()'))

    def read_code(self):
        # 部分部署公开标准 Monaco API，可以可靠读取包括空字符串在内的全文。
        # 必须按当前 DOM 的 URI 匹配，不能使用 getModels()[0] 猜测当前文件。
        self.check()
        result = self.page.evaluate('''uri => {
            const api = window.monaco?.editor;
            if (typeof api?.getModels !== 'function') return null;
            const models = api.getModels().filter(model => model.uri.toString() === uri);
            if (models.length !== 1) return null;
            return {code: models[0].getValue()};
        }''', self.uri)
        if result is not None:
            self.check()
            if not isinstance(result, dict) or not isinstance(result.get('code'), str):
                raise ValueError('Monaco API 返回的代码格式无效。')
            return normalize(result['code'])
        with self.clipboard():
            return self._read()

    def set_code(self, code):
        code = normalize(code)
        if not code.strip():
            raise ValueError('本地代码为空，不写入。')
        if (not self.input.is_editable() or self.input.get_attribute('aria-readonly') == 'true'
                or self.root.get_attribute('aria-readonly') == 'true'):
            raise ValueError('代码编辑器为只读，停止写入。')
        with self.clipboard():
            self.check()
            self.input.focus()
            self.page.keyboard.press('Control+a')
            self.page.evaluate('text => navigator.clipboard.writeText(text)', code)
            self.page.keyboard.press('Control+v')
            self.page.wait_for_timeout(500)
            actual = self._read()
            if actual != code:
                raise ValueError('编辑器回读与本地代码不一致，禁止评测。')
            self.page.keyboard.press('ArrowRight')
        return actual
