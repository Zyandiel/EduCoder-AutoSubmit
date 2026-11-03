"""DeepSeek 解题服务与仅保存在本机的凭据。"""
from .client import AIError, AiOptions, DeepSeekClient
from .credentials import configure_api_key, get_api_key

__all__ = ["AIError", "AiOptions", "DeepSeekClient", "configure_api_key", "get_api_key"]
