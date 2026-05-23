# FlowMate

基于 **FastAPI + Chainlit** 的个人工作智能助理，集成 DeepSeek Function Calling、三平台求职数据同步（Boss直聘 + 智联招聘 + 猎聘）、日报自动生成、搜索引擎、数据可视化等能力。

## 功能一览

### 📮 求职管理（Boss直聘 + 智联招聘 + 猎聘）

| 指令 | 功能 |
|------|------|
| `同步投递` | 三平台今日投递（Boss: 沟通过/已投递/面试/感兴趣 + 智联: 已投递/收藏 + 猎聘: 已投递/已查看/面试/收藏） |
| `同步推荐` | 三平台每日推荐 |
| `同步Boss` / `同步智联` / `同步猎聘` | 单平台同步投递 |
| `同步Boss推荐` / `同步智联推荐` / `同步猎聘推荐` | 单平台同步推荐 |
| `投递汇总` | 全部平台投递统计 |
| `投递表` / `每日推荐表` | 列表展示岗位（最多10条） |
| `导出Excel` | 三平台导出（按日期，默认今天） |
| `导出Boss` / `导出智联` / `导出猎聘` | 单平台导出（Excel 含公司/职位超链接） |
| `图表` / `投递趋势` / `平台对比` | ASCII 可视化 |

### 🔐 Cookie 管理

| 指令 | 功能 |
|------|------|
| `查看配置` | 实时探测三平台 Cookie 有效性（✅有效 / ⚠️过期 / ❌未配置） |
| `检查Cookie` | 一键诊断三平台 Cookie 状态 |
| `更新Boss Cookie` / `更新智联Cookie` / `更新猎聘Cookie` | 更新登录态（直接粘贴 Cookie 自动识别平台） |
| `刷新猎聘` | 生成 Cookie 刷新脚本 |

### 📄 日报与总结

| 指令 | 功能 |
|------|------|
| `生成日报` | 投递数据 + 投递分析建议 + 今日总结 + 技能推荐 → Markdown |
| `项目总结` | 读对话 + devlog.md + 上传文件 → 开发简报 |
| `导入开发日志` | 加载 devlog.md 参与总结 |

### 🔍 搜索引擎

| 指令 | 功能 |
|------|------|
| `搜索Redis Stream最佳实践` | 实时 DuckDuckGo 搜索，返回文章链接+摘要 |
| `帮我查一下LangChain` | 同上 |

### ⚙️ 配置管理

| 指令 | 功能 |
|------|------|
| `查看配置` | 表格化配置中心（模型/Key/三平台Cookie状态/GitHub） |
| `用DeepSeek` / `用OpenAI` / `用智谱` | 一键切换 AI 模型（自动填 API 地址） |
| `设置Key为sk-xxx` | 配置 API Key |
| `更新Boss Cookie` | 更新登录态（支持直接粘贴 Cookie 内容） |
| `设置GitHub Token为ghp_xxx` | 配置代码推送 |
| `切换用户 用户名` | 多用户独立配置 |
| `刷新猎聘` | 生成 Cookie 刷新脚本 |

**支持的 AI 模型**：DeepSeek、OpenAI、智谱 GLM、Moonshot、自定义（任何兼容 OpenAI 接口的服务）

### 📁 文件上传（13种格式）

拖拽 `md / txt / json / log / py / csv / html / yaml / pdf` 等文件到对话框，自动安全存储并纳入日报分析。

### 🔧 其他

| 指令 | 功能 |
|------|------|
| `搜索历史对话` | 查找历史聊天记录 |
| `提交代码到 GitHub` | git add + commit + push 一键推送 |
| `帮助` / `你能做什么` | 功能介绍 |
| `python cli.py sync` | 命令行模式（不需打开 Chat） |

### 🧠 智能特性

- **128K 上下文**：充分利用 DeepSeek 长窗口
- **记忆压缩**：超 200K 字符自动摘要旧对话，保留最近 10 轮
- **规则热加载**：编辑 `rules.md` 即时调整 Agent 行为，不用重启
- **聊天持久化**：刷新页面自动恢复最近对话
- **新用户引导**：首次启动检测未配 Key → 弹出引导 → 说跳过不再提醒
- **Cookie 实时验证**：配置页面对三平台 Cookie 做真实 API 探测，不再只检查字段是否存在
- **智能 Cookie 识别**：直接粘贴浏览器 Cookie 内容，自动识别 Boss/智联/猎聘并保存
- **今日过滤**：同步和导出默认只处理今天的数据，投递/收藏按时间戳过滤，推荐始终算当天

## 项目结构

```
agent/
├── agent.py               # Agent 核心（记忆压缩 + 规则热加载）
├── boss.py                # Boss直聘 5 模块 + Excel 导出（含公司/职位超链接）
├── zhaopin.py             # 智联招聘 3 模块 + Excel 导出（含链接）
├── liepin.py              # 猎聘 5 模块 + Excel 导出（含链接）
├── skills.py              # 41 项技能 + OpenAI Function Calling 定义
├── settings.py            # 模型/Key/Cookie/Token 配置管理 + Cookie 实时验证
├── tools.py               # 搜索引擎 + 浏览器自动化
├── charts.py              # ASCII 数据可视化
├── cli.py                 # 命令行工具
├── git_ops.py             # Git 操作
├── config.py              # AI 模型配置
├── storage.py             # JSON 持久化（跨会话去重）
├── chainlit_app.py        # Chainlit UI（Python 3.14 补丁 + 文件上传 + 历史持久化 + 帮助系统 + Cookie 自动识别）
├── rules.md               # Agent 行为规则（热加载，编辑即生效）
├── app.py                 # FastAPI 接口
├── users.json             # 多用户配置（.gitignore 排除）
├── devlog.md              # 开发日志（.gitignore 排除）
├── tests/                 # 12 个核心测试用例
└── data/                  # 数据目录（.gitignore 排除）
    ├── conversations/     # 按日对话记录 JSON
    ├── applications.json  # 投递记录（加密 ID + 状态组合去重）
    ├── uploads/           # 用户上传文件
    ├── chat_history.json  # 聊天持久化
    └── reports/
        ├── daily/         # 工作日报 .md
        ├── boss/          # Boss直聘 Excel
        ├── zhaopin/       # 智联招聘 Excel
        └── liepin/        # 猎聘 Excel
```

## 技术栈

| 层 | 技术 |
|---|---|
| 对话界面 | Chainlit 2.11 |
| AI 推理 | DeepSeek / OpenAI / 智谱 GLM / Moonshot（OpenAI SDK） |
| Agent 调度 | OpenAI Function Calling（tool_choice=auto） |
| 数据存储 | JSON 文件（按平台/日期分布，跨会话去重） |
| Excel 导出 | openpyxl（含超链接） |
| PDF 解析 | PyMuPDF |
| 搜索引擎 | DuckDuckGo（ddgs） |
| 浏览器抓取 | requests + Cookie 认证（多端点，猎聘含 X-Fscp 反爬） |
| 测试 | unittest（标准库） |
| 版本管理 | Git + GitHub |

## 快速开始

```bash
# 1. 虚拟环境
python3 -m venv .venv && source .venv/bin/activate

# 2. 安装
pip install -r requirements.txt

# 3. 启动
chainlit run chainlit_app.py --headless --port 8000
```

首次启动自动弹出引导界面，依次选择模型、设置 API Key 即可使用。招聘平台同步需额外配置对应 Cookie。

## 命令行模式

```bash
python cli.py sync               # 同步全部投递（仅今天）
python cli.py sync --recommend   # 同步全部推荐
python cli.py sync --boss        # 只同步Boss
python cli.py sync --zhaopin     # 只同步智联
python cli.py sync --liepin      # 只同步猎聘
python cli.py export             # 导出全部 Excel（默认今天）
python cli.py export --delivery  # 只导出投递
python cli.py export --recommend # 只导出推荐
python cli.py chart              # 全部图表
python cli.py report             # 生成日报
```

## 隐私说明

以下敏感文件已通过 `.gitignore` 排除，永远不会提交到 GitHub：

| 文件 | 内容 |
|---|---|
| `.env` | AI API Key、模型选择 |
| `users.json` | 招聘平台 Cookie、多用户配置 |
| `.git/config` | GitHub Token |
| `data/` | 对话记录、投递数据、日报、Excel |
| `devlog.md` | 开发日志 |

## License

MIT
