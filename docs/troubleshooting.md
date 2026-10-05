# 常见问题

## 找不到 `.venv\Scripts\python.exe`

先进入项目目录。首次双击 `START.cmd` 会创建环境；事先安装 Python 3.11+。PowerShell 使用 `Get-Location` 查看当前位置。

## 首次启动只生成配置

这是初始化流程。编辑 `config.local.yaml` 的课程地址和 `assignments`，把代码放入 `solutions/` 后再运行。需要准确名称时先登录并执行 `list`。

## 浏览器未安装或启动失败

确认 `browser_channel` 对应浏览器存在：`chrome` 需要 Chrome，`msedge` 需要 Edge。选择 `chromium` 后执行 `python -m playwright install chromium`。启动器安装 Python 依赖，但不会安装 Chrome。

## 会话失效、登录页或验证码

双击 `LOGIN.cmd`，或执行 `python main.py login --fresh`，手动完成验证，确认身份后输入 `save`。保存文件存在不证明会话仍有效。程序不绕过权限或验证页面。

## 找不到按钮、编辑器或关卡

先手动确认页面可访问，检查 `debug/screenshots/`。当前适配已核实的 Monaco DOM；改版或其他编辑器会报错。开启 `debug: true` 并用 `inspect` 收集脱敏信息，不盲目改 selector 或发送含凭据的完整 HTML。

## 文件缺失或映射错误

目录名与实训名称完全一致，文件名为 `1.cpp`、`2.cpp` 等。`.files.json` 左侧路径与网站菜单一致，右侧文件位于实训目录内。先执行 `auto --check`。

## 写入后代码不一致

运行期间避免使用剪贴板、切换在线文件或编辑该浏览器。程序通过 Monaco 操作和剪贴板回读校验；不一致时不会评测。不同布局可能需要适配。

## 评测失败或超时

检查 `logs/run-*/report.json` 和对应代码备份、结果文本。评测不会自动重试；先人工排查框架、编译错误、网络与测试结果。dry-run 的评测同样影响平台进度。

## 提示已有任务运行

等待前一个流程结束。锁由进程持有，退出后自动释放；`auto.lock` 文件存在本身不代表被占用。避免开启多个自动化流程。

## 最终提交或新题答案

当前自动处理已准备的本地代码，最终提交入口尚未开放。新题需要增加解答并启用配置。已完成关卡会跳过。
