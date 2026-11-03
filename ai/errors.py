class AIError(RuntimeError):
    """可以安全显示给用户的错误；不携带 API 响应正文或密钥。"""

    def __init__(self, message, *, fatal_run=False):
        super().__init__(message)
        self.fatal_run = fatal_run
