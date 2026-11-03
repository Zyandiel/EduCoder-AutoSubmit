# 使用指南

## 一键启动

Windows 用户双击 `START.cmd`：启动器创建虚拟环境、安装依赖，然后执行 `main.py start`。首次运行按提示输入 DeepSeek API Key，在浏览器登录并打开课程的“实训作业”页，确认后即可运行。已有课程配置与有效会话会复用。

命令行等价操作：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py start
```

无需激活虚拟环境或修改 PowerShell 执行策略。Windows 启动向导优先使用已安装的 Chrome/Edge；缺少可用浏览器时自动下载 Playwright Chromium。直接运行 `auto` 时，需已有可用浏览器。

## API Key

运行 `python main.py setup` 输入或更换 Key。Windows 输入不回显，密钥使用当前 Windows 用户的 DPAPI 加密，保存在被 Git 忽略的 `.auth/`。这不是头歌账号密码；课程尚未设置时，`setup` 也会引导选择课程。

也可由进程环境提供 `DEEPSEEK_API_KEY`，优先级高于本机保存的密钥。非 Windows 环境使用该环境变量；不要把实际密钥写进仓库、日志或命令示例。`auto --check` 只检查本机能否读取 Key，不验证余额或向 API 发请求。

请求发送到官方 DeepSeek Chat Completions API。默认模型 `deepseek-flash`，使用 JSON 输出，并由客户端检查文件路径、文件内容与返回状态。模型名可在配置中调整，支持情况以 [DeepSeek 官方文档](https://api-docs.deepseek.com/api/create-chat-completion/)为准。

## 本地配置

`start` 会创建缺少的配置。也可运行 `init` 从 [config.example.yaml](../config.example.yaml) 创建 `config.local.yaml`；已有文件不会覆盖。默认优先读取 `config.local.yaml`，其次兼容旧版 `config.yaml`。相对路径以配置文件所在目录为基准。

自定义配置放在子命令前：`python main.py --config config.local.other.yaml start`。

| 配置项 | 说明 |
| --- | --- |
| `course_url` | 目标课程的 `https://www.educoder.net/classrooms/.../shixun_homework` 地址；首次引导可从浏览器获取 |
| `ai.enabled` | 默认 `true`，根据题目生成解答；`false` 使用本地代码 |
| `ai.model` | 默认 `deepseek-flash` |
| `ai.timeout_seconds` | 单次 API 请求超时，默认 180 秒 |
| `ai.max_tokens` | 单次生成上限，默认 16000 |
| `ai.max_calls_per_run` | 每次运行 API 调用上限，默认 100；达到上限后停止生成 |
| `ai.max_context_chars` | 题目及模板字符上限，默认 160000；过大时报错，不静默截断题目 |
| `assignment_scope` | AI 模式默认 `all`；`configured` 仅处理配置中启用的作业 |
| `assignments` | 可选，完整名称及 `enabled: true/false`；全量模式可用 `false` 排除作业 |
| `solutions_dir` | 本地代码模式目录；AI 模式不要求存在答案 |
| `session_file` | storageState 路径；含登录凭据 |
| `dry_run` | 保持 `true`；当前版本不执行最终提交 |
| `debug` | 输出步骤、显示浏览器并保存诊断截图 |
| `headless` | 仅在非交互且 `debug: false` 时生效 |
| `browser_channel` | `chrome`、`msedge` 或 `chromium` |
| `navigation_timeout_ms` | 页面导航超时，默认 60000 毫秒 |
| `action_timeout_ms` | 普通页面动作超时，默认 15000 毫秒 |

无需列出每个新作业。全量模式会在每次启动时扫描所有分页，分别处理同名、不同详情地址的作业。若只处理选定作业，可设置：

```yaml
assignment_scope: configured
assignments:
  - name: "你的实训名称"
    enabled: true
```

显式 `--assignment "名称"` 优先于配置的启用状态；同名作业会按各自详情地址分别处理。

## 自动解题流程

```powershell
.\.venv\Scripts\python.exe main.py auto --check
.\.venv\Scripts\python.exe main.py auto
.\.venv\Scripts\python.exe main.py run --assignment "你的实训名称" --dry-run
```

`auto` 和 `run` 刷新作业列表，检查关卡状态，只进入需要处理的工作区。程序使用页面上实际的“上一关/下一关”链接定位关卡，读取题目说明与在线文件菜单中的模板，将这些内容发送到 DeepSeek。

AI 返回的修改文件必须属于刚刚读取的可编辑文件。未知路径、只读文件、重复文件或格式异常会停止当前题目，不写入网站。合法输出自动保存在运行记录中；写入前重新核对题目和模板，备份原代码，逐个填写并回读验证。只有代码一致才点击评测。

每关只评测一次。通过后继续下一关；失败、未知状态、重复关卡或超时会记录问题并继续其他作业。本次运行不自动反复生成和评测同一关。API Key 无效、额度不足、限流或达到调用上限时，应先解决原因再重新启动。

模型不能补足未提供的教材内容。如果题目依赖缺失上下文或只展示图片，可能需要人工补充信息。程序不会解锁参考答案或绕过访问限制；不能保证所有生成代码一次通过。

`dry_run: true` 允许写代码、评测并更新平台进度。最终提交尚未实现，`submit` 始终退出 2；关闭 dry-run 不会自动开放提交。

## 登录与诊断

```powershell
.\.venv\Scripts\python.exe main.py login --fresh
.\.venv\Scripts\python.exe main.py list
```

独立 `login` 命令在浏览器中手动登录，确认身份后输入 `save`；`q` 取消保存。`--fresh` 忽略旧会话，仅在确认保存后替换文件。会话过期或出现验证码时按提示重新登录，文件存在不证明会话仍有效。

`list` 读取全部分页并正常点击标题取得详情地址，保存到 `logs/assignments.json`。`completed` 表示关卡进度，未知时为 `null`，不证明最终提交；`can_submit` 当前为 `null`。`scan_complete` 表示列表是否完整。

课程诊断：`python main.py inspect --html`，确认 `capture` 后保存。作业诊断：`python main.py inspect --assignment "名称" --enter --html`，只读取并进入工作区。进入实训可能累计平台学习用时。

## 可选：使用自己写好的代码

运行 `python main.py auto --local`，或在配置中设置 `ai.enabled: false`。本地模式按 `assignments` 中启用的名称运行，也可使用 `--assignment` 显式指定。

```text
solutions/
└── 你的实训名称/
    ├── 1.cpp
    ├── 2.cpp
    └── greeting.h
```

第 N 关读取 UTF-8 的 `N.cpp`，保留题目要求的框架与标记。只要求函数或头文件的关卡，无需额外添加 `main`。缺少本地代码时跳过并记录，不自动改用 AI。

多文件关卡可添加同名 `N.files.json`：

```json
{
  "step2/main.cpp": "2.cpp",
  "step2/greeting.h": "greeting.h"
}
```

左侧为网页文件菜单中的完整路径，右侧为实训目录内的相对文件路径；这只是布局示例。缺失文件、空文件或跨目录路径会报错，未映射的辅助头文件不会自动上传。参考 [完整示例](../examples/solutions/)。AI 模式自动生成映射，无需手工准备这些文件。

## 日志与退出码

| 文件 | 内容 |
| --- | --- |
| `logs/日期.log` | 动作、调用用量与异常 |
| `logs/auto-summary.json` | 一键运行范围、跳过项目与退出码 |
| `logs/run-*/report.json` | 逐关状态、校验值与评测结果 |
| `logs/run-*/*/generated/` | 自动生成的代码和文件映射 |
| `logs/run-*/*/` | 题目、原代码、生成结果与评测文本 |
| `debug/screenshots/` | 截图及 URL 元数据 |
| `.auth/` | 本机加密 API Key 和网站登录状态；不要分享 |

截图、HTML、题目与代码可能含个人信息，分享前脱敏。网站登录状态包含 Cookie、localStorage、IndexedDB，不包含 sessionStorage，不保证所有登录方式永久恢复。

| 退出码 | 含义 |
| --- | --- |
| `0` | 命令完成；可能全部跳过已完成作业 |
| `1` | 配置、密钥、文件或浏览器错误 |
| `2` | 最终提交入口未实现，或命令行参数错误 |
| `3` | 列表不完整、指定作业未找到或运行存在失败项 |
| `130` | 用户取消或终端输入结束 |
