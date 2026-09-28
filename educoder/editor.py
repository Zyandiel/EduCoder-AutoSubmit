"""实际页面没有 Monaco 全局 API；使用正常键盘粘贴并完整回读。"""
import uuid
from contextlib import contextmanager
from urllib.parse import urlsplit


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
        self.page.wait_for_function('async marker => (await navigator.clipboard.readText()) !== marker', arg=marker, timeout=5000)
        return normalize(self.page.evaluate('navigator.clipboard.readText()'))

    def read_code(self):
        with self.clipboard():
            return self._read()

    def set_code(self, code):
        code = normalize(code)
        if not code.strip():
            raise ValueError('本地代码为空，不写入。')
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
