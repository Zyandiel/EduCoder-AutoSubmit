# 使用指南

## 安装与初始配置

Windows 用户可使用 `START.cmd`。命令行安装方式：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py init
```

首次 `init` 从 `config.example.yaml` 创建 `config.local.yaml`，重复执行保留已有内容。默认优先读取 `config.local.yaml`，其次读取兼容的 `config.yaml`。相对路径以配置文件所在目录为基准。无需激活虚拟环境或修改 PowerShell 执行策略。

自定义配置放在子命令前：`python main.py --config config.local.other.yaml list`。

| 配置项 | 说明 |
| --- | --- |
| `course_url` | 课程的 `https://www.educoder.net/classrooms/.../shixun_homework` 地址 |
| `solutions_dir` | 本地代码目录 |
| `session_file` | storageState 路径；含登录凭据 |
| `assignments` | 完整作业名称与 `enabled: true/false` |
| `dry_run` | 保持 `true`；自动模式拒绝最终提交 |
| `debug` | 输出步骤、显示浏览器、保存诊断截图 |
| `headless` | 仅在非交互且 `debug: false` 时生效 |
| `browser_channel` | `chrome`、`msedge` 或 `chromium` |
| `navigation_timeout_ms` | 页面导航超时，默认 60000 毫秒 |
| `action_timeout_ms` | 普通页面动作超时，默认 15000 毫秒 |

`chrome` / `msedge` 使用已安装浏览器。选择 `chromium` 时先执行 `python -m playwright install chromium`。程序使用独立浏览器上下文，不加载日常浏览器的用户配置。

## 会话与作业列表

```powershell
.\.venv\Scripts\python.exe main.py login
.\.venv\Scripts\python.exe main.py list
```

登录在浏览器中手动完成；确认身份后输入 `save`。输入 `q` 取消保存。`login --fresh` 忽略旧会话，只有确认保存才替换旧文件。登录有效性由用户在网页确认。

`list` 读取列表与分页，正常点击标题取得详情地址，保存到 `logs/assignments.json`。`completed` 是关卡进度，可以为未知值 `null`；不证明最终提交。`can_submit` 当前为 `null`。`scan_complete` 表示读取完整性，错误记录在 `error` 字段中。

## 本地代码与多文件映射

目录名必须与作业名称一致。第 N 关读取 `N.cpp`，按 UTF-8 保存。保留题目要求的框架或标记；只要求函数或头文件的关卡无需额外添加 `main`。

单文件关卡写入当前在线文件。多文件关卡添加同名 `N.files.json`：

```json
{
  "step2/main.cpp": "2.cpp",
  "step2/greeting.h": "greeting.h"
}
```

左侧必须是实际网页文件菜单中的完整路径，右侧是当前实训目录下的本地相对路径。这些是布局示例，使用前按实际关卡修改。所有映射文件在修改网页前检查；缺失文件、空文件或跨目录路径会报错。未映射的辅助头文件不会自动上传。参考 [完整示例](../examples/solutions/)。

## 自动运行与指定作业

```powershell
.\.venv\Scripts\python.exe main.py auto --check
.\.venv\Scripts\python.exe main.py auto
.\.venv\Scripts\python.exe main.py run --assignment "你的实训名称" --dry-run
```

`auto` 每次刷新列表；`run` 使用已有列表缓存，课程改变或链接失效时先重新执行 `list`。`enabled` 控制默认处理范围，显式 `--assignment` 优先。

`auto --check` 检查启用配置和已有代码，包括映射；不连接站点、不编译 C++，不能证明题目通过。缺少代码会警告，正常运行时该作业跳过。

流程重新读取关卡状态，用页面“上一关/下一关”定位最早未完成关卡。回读一致后只点击一次评测，等待本次更新的结果。成功要求成功样式、非零且全部通过的测试数和“全部通过”文字。失败、状态未知、重复关卡或超时停止该作业，继续其他启用作业。

`dry_run: true` 允许写代码、评测并更新平台进度。最终提交尚未实现；`submit` 始终退出 2，`run` 在未开启 dry-run 时会在操作前报错。

## 日志、诊断与退出码

| 文件 | 内容 |
| --- | --- |
| `logs/日期.log` | 动作和异常 |
| `logs/auto-summary.json` | 一键运行范围、跳过项目和退出码 |
| `logs/run-*/report.json` | 逐关动作、校验值和评测结果 |
| `logs/run-*/*/` | 原代码、本地代码和结果文本 |
| `debug/screenshots/` | 截图及 URL 元数据 |
| `.auth/storage_state.json` | Cookie、localStorage、IndexedDB；含登录凭据 |

截图、HTML 和日志可能含个人信息或代码，分享前脱敏。storageState 不包含 sessionStorage，不保证所有登录方式永久恢复。

课程诊断：`python main.py inspect --html`，确认 `capture` 后保存。作业诊断：`python main.py inspect --assignment "名称" --enter --html`，只读取并进入工作区。进入实训可能累计平台学习用时。

| 退出码 | 含义 |
| --- | --- |
| `0` | 命令完成；自动流程可能全部跳过已完成作业 |
| `1` | 配置、文件或浏览器错误 |
| `2` | 最终提交入口未实现，或命令行参数错误 |
| `3` | 列表不完整、配置作业未找到或运行存在失败项 |
| `130` | 用户取消或终端输入结束 |
