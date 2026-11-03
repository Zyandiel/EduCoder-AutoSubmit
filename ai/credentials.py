"""环境变量优先；Windows 使用当前用户的 DPAPI 加密保存 Key。"""
import ctypes
import getpass
import os
import tempfile
import warnings
from pathlib import Path

from .errors import AIError

KEY_ENV = "DEEPSEEK_API_KEY"
KEY_FILE = "deepseek-key.dat"
_ENTROPY = b"EduCoder-AutoSubmit/DeepSeek/v1"


def validate_key(value):
    if not isinstance(value, str):
        raise AIError("DeepSeek API Key 必须是字符串。", fatal_run=True)
    value = value.strip()
    if not 8 <= len(value) <= 512 or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise AIError("DeepSeek API Key 格式无效，请重新配置；不要输入空格或换行。", fatal_run=True)
    return value


class _Blob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data):
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _protect(data, *, decrypt=False):
    if os.name != "nt":
        raise AIError("当前系统请通过 DEEPSEEK_API_KEY 环境变量提供 Key。", fatal_run=True)
    # 保留输入/entropy 缓冲区直到调用完成，输出由 LocalFree 释放。
    source, source_buffer = _blob(data)
    entropy, entropy_buffer = _blob(_ENTROPY)
    output = _Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        function = crypt.CryptUnprotectData
        second_type = ctypes.POINTER(ctypes.c_wchar_p)
    else:
        function = crypt.CryptProtectData
        second_type = ctypes.c_wchar_p
    function.argtypes = [ctypes.POINTER(_Blob), second_type, ctypes.POINTER(_Blob),
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_Blob)]
    function.restype = ctypes.c_int
    if not function(ctypes.byref(source), None, ctypes.byref(entropy), None, None,
                    0x1, ctypes.byref(output)):  # CRYPTPROTECT_UI_FORBIDDEN
        raise AIError("本机 Key 无法解密或保存，请运行 python main.py setup 重新配置。", fatal_run=True)
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))


def save_api_key(root: Path, key: str):
    """仅写入 DPAPI 密文；失败时不会覆盖原有密钥文件。"""
    encrypted = _protect(validate_key(key).encode("utf-8"))
    path = Path(root) / ".auth" / KEY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".deepseek-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encrypted)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def get_api_key(root: Path):
    value = os.environ.get(KEY_ENV)
    if value and value.strip():
        return validate_key(value)
    path = Path(root) / ".auth" / KEY_FILE
    if not path.is_file():
        return None
    if os.name != "nt":
        raise AIError("本地 Key 属于 Windows 用户，请设置 DEEPSEEK_API_KEY 环境变量。", fatal_run=True)
    try:
        if path.stat().st_size > 16_384:
            raise AIError("本地 Key 文件损坏，请重新配置。", fatal_run=True)
        return validate_key(_protect(path.read_bytes(), decrypt=True).decode("utf-8"))
    except (OSError, UnicodeError):
        raise AIError("无法读取本地 Key，请运行 python main.py setup 重新配置。", fatal_run=True) from None


def configure_api_key(root: Path):
    """不在 YAML/命令行参数中接收或回显密钥。"""
    if os.name != "nt":
        key = get_api_key(root)
        if key:
            print("已从 DEEPSEEK_API_KEY 环境变量读取 Key。")
            return key
        raise AIError("请先设置 DEEPSEEK_API_KEY 环境变量，再运行自动流程。", fatal_run=True)
    print("输入 DeepSeek API Key（不回显；使用 Windows 当前用户加密后保存在 .auth 中）。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = validate_key(getpass.getpass("DeepSeek API Key: "))
    except getpass.GetPassWarning:
        raise AIError("当前终端不支持隐藏输入，请在 PowerShell 运行 setup，或设置 DEEPSEEK_API_KEY。", fatal_run=True) from None
    save_api_key(root, key)
    print("DeepSeek API Key 已加密保存。")
    if os.environ.get(KEY_ENV, "").strip():
        print("注意：当前 DEEPSEEK_API_KEY 环境变量仍优先于刚保存的 Key。")
        return get_api_key(root)
    return key
