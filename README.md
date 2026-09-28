# EduCoder 编程作业助手

GitHub 仓库包含程序和说明；本地答案、登录会话、运行日志和截图不随仓库上传。克隆后请自行准备 `solutions/` 中的代码，修改 `config.yaml` 为自己的课程并手动登录。下面的58关完成记录是原本机验证记录，不代表克隆后自带答案。

## 双击运行

在项目文件夹中双击 **START.cmd**。它会自动切换工作目录、检查 Python 环境及依赖、恢复会话、刷新作业列表，并依次填写和评测配置中未完成的关卡。已经完成的作业会跳过；重复双击会被运行锁阻止。

首次使用需要安装 Python 3.11+ 和 Google Chrome。没有保存会话时会提示手动登录，在终端输入 `save` 后继续。会话失效时按提示输入 `login`，或双击 **LOGIN.cmd** 重新登录。验证码仍需手动完成。

一键模式使用 `solutions/` 中现有代码，不包含在线生成答案服务。新增题目需要补齐本地解答并在 `config.yaml` 中启用。缺少代码、评测失败或页面无法识别会记录错误，不反复评测。保持 `dry_run: true`；评测会保存代码并更新关卡进度，但不会点击最终提交。

结果见 `logs/auto-summary.json` 和 `logs/run-*/report.json`。仅检查本地文件、不打开浏览器：运行 `START.cmd --check`。也可以使用 `.\.venv\Scripts\python.exe main.py auto`。

Python + Playwright，面向 Windows。当前完成**登录、作业/关卡识别、Monaco 代码写入与回读、多文件填写、单次评测**。CLI 读取本地代码，不内置答案生成服务。

2026-09-27：原9个实训的33关及后来确认继续处理的10个实训25关均已完成，重新读取全部详情确认 **19个实训、58/58关全部通过**。本地代码位于 `solutions/`，清单见 `COMPLETION.md`，逐关状态见 `logs/catalog.json`，文件校验值见 `logs/completion.json`。保持 `dry_run: true`，没有执行最终提交。

`list`、`inspect` 和 `run --dry-run` 已实现。最终提交仍未开放，`submit` 返回退出码 2；关闭 dry-run 时 `run` 会在操作前报错，请勿把当前版本视为完整自动提交工具。

## 填写和评测

```powershell
cd E:\EduCoder-AutoSubmit
.\.venv\Scripts\python.exe main.py run --assignment "C++之递归函数应用" --dry-run
```

不指定 `--assignment` 时处理配置中 `enabled: true` 的作业。每个作业先读实际关卡状态，进入当前未完成关卡，加载对应 `N.cpp`，备份在线代码后写入并逐字回读校验。只有校验一致才单击一次评测。只接受本次点击后更新的测试结果区域；要求成功样式、非零且全部通过的测试数、以及“全部通过”同时成立。没有确认新结果会超时，不重试评测。

通过后重新读取作业详情，进入工作区并使用页面的“上一关/下一关”链接定位最早未完成关卡；当前关卡重复、状态不明、失败或缺少代码时停止该作业，继续其他配置作业。已完成作业跳过。运行日志保存在 `logs/run-日期时间/`，包含 `report.json`、本地代码、原在线代码、结果或错误信息。存在缺失文件或失败时返回非零退出码。

真实站点已核实本课程19个实训全部58关通过，使用 Monaco 编辑器。该站点未暴露 `window.monaco`，因此通过编辑器键盘全选/粘贴写入，复制回读；临时使用系统剪贴板并在结束后恢复原剪贴板文本。运行时请勿同时编辑浏览器或使用剪贴板。其他编辑器类型尚未验证，遇到不支持的 DOM 会停止，不能假定任意 textarea 是代码编辑器。

`dry_run` 允许写入并运行平台评测，评测本身会保存代码并更新关卡进度/成绩；它只禁止最终“提交作业”。目前所有最终提交入口均未实现，日志中的通过记录也不会自动授权提交。

## 安装与启动（PowerShell）

建议 Python 3.11 或更新版本。在当前项目目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\Activate.ps1
python main.py login
```

若 PowerShell 禁止激活脚本，直接使用 `.\.venv\Scripts\python.exe main.py login`，不必修改系统执行策略。

首次启动会打开可见的 Chromium。手动完成账号登录、验证码和网站验证；确认页面显示你的登录身份后，在终端输入 `save`。程序保存会话并关闭浏览器。输入 `q`、Ctrl+C 或终端输入结束会取消保存。

当前这台 Windows 的 Playwright 1.62 配套可见 Chromium 报组件错误，已固定依赖为 1.58.0。由于对应浏览器下载缓慢，当前配置 `browser_channel: chrome` 使用本机已安装的 Google Chrome（Chromium 内核），无需等待配套浏览器下载。它使用独立的临时浏览器上下文，不读取你日常 Chrome 的用户配置。若想使用 Playwright 配套 Chromium，请安装完成后改为 `browser_channel: chromium`；也支持已安装的 `msedge`。

配套 Chromium 的安装命令是 `.\.venv\Scripts\python.exe -m playwright install chromium`。本机该下载已取消；当前默认配置不需要它。

以后执行 `login` 或 `inspect` 会加载 `.auth/storage_state.json`。会话过期时手动重新登录；文件损坏时执行 `python main.py login --fresh`。`--fresh` 忽略旧文件，只有确认保存后才会替换原文件。

**现阶段的登录成功由你人工确认**，保存文件本身不能证明登录有效。当前没有通过猜测 DOM 自动检测失效或登录成功。

## 检查课程页面

把 `config.yaml` 的 `course_url` 改为你有权访问的真实课程地址，然后运行：

```powershell
python main.py inspect
```

浏览器会恢复会话并打开课程页。确认页面加载完毕后，在终端输入 `capture`，保存当前标签页截图、去掉查询参数的 URL 和会话。它不会提取作业或点击按钮。

需要给下一阶段提供 DOM 时，可执行 `python main.py inspect --html`。确认 `capture` 后额外保存 `debug/course.html`。该文件是当前页面 DOM，不包含跨域 iframe 内部 DOM，也不导出独立的 storageState；但页面本身仍可能含个人信息或凭据，分享前务必检查。

其他配置：`debug: true` 强制显示浏览器、输出步骤并保存截图；登录和检查命令始终显示浏览器。`dry_run: true` 是默认值；目前无论该值是什么，都没有实现提交动作。相对文件路径以配置文件所在目录为基准。自定义配置用 `python main.py --config config.local.yaml login`。

## 读取实训作业

当前配置已写入你提供的课程地址。在 PowerShell 执行：

```powershell
cd E:\EduCoder-AutoSubmit
.\.venv\Scripts\python.exe main.py list
```

命令恢复登录状态，读取课程实训列表及分页，并依次点击作业标题，在新标签页读取实际详情地址后关闭。它不会点击“开始学习”“继续挑战”或“提交总结”。结果打印到终端并保存到 `logs/assignments.json`。

字段包括 `name`、`progress`、`url`、`completed`、`status`、`submission_window_open`、`can_submit` 和 `error`。`completed` 仅表示关卡进度达到总数，不证明已最终提交；`submission_window_open` 根据页面的“提交中/补交中”状态判断；`can_submit` 当前始终为 `null`（未确认），绝不能凭开放期或进度自动提交。

链接读取失败会截图、标记错误并继续其他作业；存在链接错误时 `scan_complete=false` 且退出码为 3。列表结构或分页控件无法识别时会报错，不把未知页面当作空列表成功。课程当前仅有一页；多页逻辑通过浏览器 fixture 测试，尚未在多页真实课程中验证。尚未观察过空列表/失效登录页面，因此这两类情况仅作保守报错，不自动区分。

## 本地代码目录

已增加关卡检查命令（2026-09-22）：

```powershell
cd E:\EduCoder-AutoSubmit
.\.venv\Scripts\python.exe main.py inspect --assignment "C++之递归函数应用"
.\.venv\Scripts\python.exe main.py inspect --assignment "C++之递归函数应用" --enter
```

第一条读取详情页关卡表；第二条还会点击已验证的“继续挑战”进入工作区，识别当前关卡与 Monaco 编辑器，随后关闭浏览器。进入工作区可能开始累计平台学习用时，但不修改代码、不评测或提交。结果保存到 `logs/challenges.json`。添加 `--html` 可导出当前 DOM。

已实测本课程19个实训的工作区与关卡。遇到不同入口、编辑器或未知 DOM 会停止并截图；不会猜测操作。第 N 关对应作业目录中的 `N.cpp`，内容应是要放入在线文件的完整代码（保留平台要求的框架和标记），不一定是带 main 的独立程序。本地辅助头文件用于编译检查，只有 `.files.json` 指定的文件才会作为额外文件写入网页。

多文件关卡使用同目录 `N.files.json` 映射真实网页菜单路径到本地文件。例如综合练习第二关的 `2.files.json` 分别将 `step2/fact.cpp` 映射到 `2.cpp`、`step2/fact.h` 映射到 `fact.h`。程序会正常切换菜单，备份并验证每个文件后再评测。不要删除数组第五关的 `Program/End` 标记；该关保留模板标记后才得到正确评测结果。

```text
solutions/
  C++之递归函数应用/
    1.cpp
    2.cpp
    3.cpp
  C++之函数应用/
    1.cpp
    2.cpp
```

`assignments` 配置控制 `run` 默认处理范围；显式 `--assignment` 优先于该列表。

## 日志和会话文件

- `.auth/storage_state.json`：cookie、localStorage、IndexedDB，会话凭据等同登录权限。不要分享或上传；已被 `.gitignore` 排除。文件不是加密保险库，访问权限继承 Windows 目录权限。
- `logs/`：步骤与错误日志，不输出 cookie 内容。
- `debug/screenshots/`：截图与 URL 元数据。截图可能包含姓名、课程等个人信息，分享前检查。
- storageState 不保存 sessionStorage。如果实测发现网站依赖它，需要根据观察结果扩展；不要假定任何登录方式都能永久恢复。

程序不会绕过验证码、登录验证、权限或反自动化机制；遇到验证请在浏览器手动完成。网络错误和加载超时不会自动重复评测。单个作业失败后会记录诊断并继续其他作业。

## 验证

```powershell
python -m unittest discover -s tests -v
python main.py --help
python scripts/check_browser.py
```

使用本机 Chrome 运行浏览器测试时，先执行 `$env:EDUCODER_TEST_BROWSER='chrome'`；默认测试使用 Playwright 配套 Chromium。

单元测试包含真实 Chromium 的 cookie/localStorage 保存恢复、损坏会话处理、写入失败保留旧文件以及提交入口禁用。浏览器诊断访问一次公开首页，记录实际 DOM 中的链接和按钮，保存公开首页 HTML 与截图；不登录、不操作作业。

2026-09-11 已使用用户保存的会话实际恢复并读取目标课程的 9 个实训及真实链接；详见 `VERIFICATION.md`。

## 当前限制

1. 本次19个实训58关代码已全部通过；最终可提交状态和最终提交入口仍未验证，`submit` 保持禁用。
2. 普通 `run` 依赖平台“继续挑战”选择当前关卡；若平台恢复到已完成的关卡，会保守停止，避免重评。
3. `scripts/guided_run.py` 用于人工逐关开发：打印题面，等待终端输入 `run` 才填写和评测，失败不自动重试。它会通过正常“上一关”链接回到最早未完成关卡。

如果无法访问课程 DOM：请打开该页面，然后把 DOM / screenshot / HTML 发给我。不要提供 cookie、storageState 或账号密码；分享 HTML 前检查并移除个人信息与凭据。
