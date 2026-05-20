import datetime as _dt

import storage
from config import client, OPENAI_MODEL


def _ask_ai_to_summarize(conversation: list[dict], instruction: str) -> str:
    """把对话记录发给 AI，让它按指令总结"""
    if not conversation:
        return ""

    # 把对话拼成文本
    lines = []
    for entry in conversation:
        role = "用户" if entry["role"] == "user" else "助手"
        lines.append(f"[{entry['time'][:19]}] {role}: {entry['content']}")
    conv_text = "\n".join(lines)

    prompt = f"""以下是一天的对话记录。请根据这些记录{instruction}。

要求：
- 用 Markdown 格式
- 如果记录中体现了做过的具体事情、学到的新知识、解决的问题，请分类列出
- 如果某类内容缺失，说明"无记录"
- 简洁，不要编造记录中没有的内容

对话记录：
---
{conv_text}
---"""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


# ---- Skill Implementations ----

def generate_daily_report(date: str = None) -> str:
    """生成某一天的日报并保存为 Markdown 文件"""
    if not date:
        today = _dt.date.today()
        date_str = today.isoformat()
    else:
        date_str = date
        today = _dt.date.fromisoformat(date)

    conversation = storage.load_conversation(date_str)
    applications = storage.list_applications(date_str=date_str)

    if not conversation and not applications:
        return f"{date_str} 没有对话记录和投递记录，无法生成日报。"

    # ---- Part 1: 投递记录 ----
    job_text = ""
    if applications:
        lines = ["## 📮 今日投递\n"]
        by_status = {}
        for j in applications:
            by_status.setdefault(j["status"], [])
            by_status[j["status"]].append(j)
        for status, jobs in by_status.items():
            lines.append(f"\n### {status}（{len(jobs)}家）\n")
            for j in jobs:
                line = f"- **{j['company']}** — {j['position']}"
                if j.get("notes"):
                    line += f"（{j['notes']}）"
                lines.append(line)
        job_text = "\n".join(lines)
    else:
        job_text = "## 📮 今日投递\n\n暂无投递记录。"

    # ---- Part 2: 推荐了解知识 ----
    rec_text = ""
    if conversation:
        lines = []
        for entry in conversation:
            role = "用户" if entry["role"] == "user" else "助手"
            lines.append(f"[{entry['time'][:19]}] {role}: {entry['content']}")
        conv_text = "\n".join(lines)

        prompt = f"""以下是一天的对话记录。请根据对话中涉及的技术话题、遇到的问题、讨论的方向，推荐 2-4 个值得深入了解的知识点或工具。

要求：
- 每条推荐包含：知识名称、一句话简介、推荐理由（与对话的关联）
- 优先推荐对话中明确提到但未深入的内容
- 用 Markdown 格式，简洁
- 不要编造对话中没有的内容

对话记录：
---
{conv_text}
---"""

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        rec_text = response.choices[0].message.content or ""
    else:
        rec_text = "今日无对话记录，无法生成知识推荐。"

    # ---- 拼报告 ----
    day_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]
    full_report = (
        f"# 工作日报\n\n"
        f"**日期**: {date_str} {day_name}\n\n"
        f"---\n\n"
        f"{job_text}\n\n"
        f"---\n\n"
        f"## 📚 推荐了解知识\n\n"
        f"{rec_text}\n\n"
        f"---\n"
        f"*由 WorkMate Agent 自动生成*"
    )

    filepath = storage.save_report(date_str, full_report)
    return f"日报已生成并保存到 `{filepath}`\n\n{full_report}"


def search_history(keywords: str) -> str:
    """搜索所有日期的对话记录"""
    dates = storage.list_conversation_dates()
    if not dates:
        return "没有任何对话记录。"

    results = []
    terms = [kw.strip().lower() for kw in keywords.split(",") if kw.strip()]
    for d in dates:
        conv = storage.load_conversation(d)
        for entry in conv:
            text = entry["content"].lower()
            if any(term in text for term in terms):
                results.append(f"[{d}] {entry['role']}: {entry['content'][:200]}")
                if len(results) >= 10:
                    break
        if len(results) >= 10:
            break

    if not results:
        return f'未找到包含 "{keywords}" 的对话记录。'

    return f'搜索 "{keywords}" 找到 {len(results)} 条记录：\n\n' + "\n\n".join(results)


def summarize_period(start_date: str, end_date: str) -> str:
    """汇总一段时间的对话，生成阶段总结"""
    conversation = []
    d = _dt.date.fromisoformat(start_date)
    end = _dt.date.fromisoformat(end_date)
    while d <= end:
        conversation.extend(storage.load_conversation(d.isoformat()))
        d += _dt.timedelta(days=1)

    if not conversation:
        return f"{start_date} ~ {end_date} 期间没有对话记录。"

    summary = _ask_ai_to_summarize(
        conversation,
        "生成一份阶段工作总结，包括：\n"
        "1. **主要工作** — 这段时间完成了哪些事情\n"
        "2. **技能成长** — 学到了哪些新知识\n"
        "3. **产出** — 有什么可交付的成果\n"
        "4. **下周计划** — 根据当前进展，建议下一步做什么",
    )
    if not summary:
        return "AI 总结失败，请稍后重试。"

    filepath = storage.save_report(
        f"{start_date}_to_{end_date}",
        f"# 阶段工作总结\n\n**周期**: {start_date} ~ {end_date}\n\n---\n\n{summary}",
    )
    return f"阶段总结已保存到 `{filepath}`\n\n{summary}"


# ---- 投简历相关技能 ----

def _import_boss():
    import os, sys, importlib.util
    try:
        import boss
        return boss, None
    except ImportError:
        # Chainlit 环境下 sys.path 可能不含项目目录，手动加载
        boss_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "boss.py")
        spec = importlib.util.spec_from_file_location("boss", boss_path)
        if spec and spec.loader:
            boss = importlib.util.module_from_spec(spec)
            sys.modules["boss"] = boss
            spec.loader.exec_module(boss)
            return boss, None
        return None, f"BOSS模块文件未找到: {boss_path}"
    except Exception as e:
        import traceback
        return None, f"BOSS模块加载异常: {traceback.format_exc()}"


def fetch_boss_channels() -> str:
    """获取 Boss直聘「沟通过」列表"""
    boss, err = _import_boss()
    if not boss:
        return err
    try:
        jobs = boss.fetch_boss_channels()
        n = boss._save_jobs_to_storage(jobs)
    except PermissionError as e:
        return f"⚠ Cookie 未配置或已过期：{e}"
    except Exception as e:
        return f"⚠ 获取沟通过列表失败：{e}"
    return (
        f"✅ 沟通过：获取成功，新增 {n} 条记录（接口正常）"
        if n > 0 else
        f"✅ 沟通过：获取成功，数据已是最新（无新增）"
    )


def fetch_boss_applied() -> str:
    """获取 Boss直聘「已投递」列表"""
    boss, err = _import_boss()
    if not boss:
        return err
    try:
        jobs = boss.fetch_boss_applied()
        n = boss._save_jobs_to_storage(jobs)
    except PermissionError as e:
        return "⚠ Cookie 未配置或已过期，请在 users.json 中更新 boss_cookie"
    except Exception:
        return "ℹ️ 已投递：Boss直聘接口暂不支持此模块的独立查询，可手动说「投了XX公司YY岗位」记录"

    return (
        f"✅ 已投递：获取成功，新增 {n} 条记录"
        if n > 0 else
        "ℹ️ 已投递：数据已是最新（Boss直聘此模块仅返回推荐数据，可手动记录实际投递）"
    )


def fetch_boss_interviews() -> str:
    """获取 Boss直聘「面试」列表"""
    boss, err = _import_boss()
    if not boss:
        return err
    try:
        jobs = boss.fetch_boss_interviews()
        n = boss._save_jobs_to_storage(jobs)
    except PermissionError as e:
        return "⚠ Cookie 未配置或已过期，请在 users.json 中更新 boss_cookie"
    except Exception:
        return "ℹ️ 面试：Boss直聘接口暂不支持此模块的独立查询，可手动说「XX公司约面试了」更新状态"

    return (
        f"✅ 面试：获取成功，新增 {n} 条记录"
        if n > 0 else
        "ℹ️ 面试：接口返回的是系统推荐，非真实面试邀请。如有面试，说「XX公司约面试了」记录"
    )


def fetch_boss_interested() -> str:
    """获取 Boss直聘「感兴趣」列表"""
    boss, err = _import_boss()
    if not boss:
        return err
    try:
        jobs = boss.fetch_boss_interested()
        n = boss._save_jobs_to_storage(jobs)
    except PermissionError as e:
        return f"⚠ Cookie 未配置或已过期：{e}"
    except Exception as e:
        return f"⚠ 获取感兴趣列表失败：{e}"
    return (
        f"✅ 感兴趣：获取成功，新增 {n} 条记录"
        if n > 0 else
        f"✅ 感兴趣：获取成功，数据已是最新（无新增）"
    )


def boss_job_summary() -> str:
    """汇总四个模块数据，输出统计报告"""
    boss, err = _import_boss()
    if not boss:
        return err
    return boss.boss_job_summary()


def export_boss_excel(status: str = None, date: str = None) -> str:
    """导出 Boss直聘 投递记录为 Excel 文件"""
    boss, err = _import_boss()
    if not boss:
        return err
    return boss.export_excel(status_filter=status, date_filter=date)


def list_exported_files() -> str:
    """列出历史导出的 Excel 文件"""
    boss, err = _import_boss()
    if not boss:
        return err
    return boss.list_exports()


# ---- Git 操作 ----

def _import_gitops():
    import os, sys, importlib.util
    try:
        import git_ops
        return git_ops, None
    except ImportError:
        gp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "git_ops.py")
        spec = importlib.util.spec_from_file_location("git_ops", gp)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules["git_ops"] = mod
            spec.loader.exec_module(mod)
            return mod, None
        return None, f"Git 模块文件未找到: {gp}"
    except Exception as e:
        import traceback
        return None, f"Git 模块加载异常: {traceback.format_exc()}"


def git_push_project(message: str) -> str:
    """将项目更新推送到 GitHub"""
    mod, err = _import_gitops()
    if not mod:
        return err
    return mod.git_push(message)


def git_display_status() -> str:
    """查看 Git 仓库当前状态"""
    mod, err = _import_gitops()
    if not mod:
        return err
    return mod.git_status()


# ---- 项目总结 ----

def generate_project_summary(date: str = None) -> str:
    """根据对话记录生成项目开发总结"""
    if not date:
        date = _dt.date.today().isoformat()

    conversation = storage.load_conversation(date)
    devlog = _load_devlog(date)

    if not conversation and not devlog:
        return f"{date} 没有对话记录和开发日志，无法生成项目总结。"

    lines = []
    for entry in conversation:
        role = "用户" if entry["role"] == "user" else "助手"
        lines.append(f"[{entry['time'][:19]}] {role}: {entry['content']}")
    if devlog:
        lines.append(f"\n[开发日志] {devlog}")
    conv_text = "\n".join(lines)

    prompt = f"""以下是一天的项目开发对话记录。请从中提炼生成一份项目开发简报，格式如下：

# 项目开发简报 — {date}

## 1. 新增功能
（从对话中提取今天新增了哪些功能模块、技能、文件）

## 2. 修复的问题
（提取修复了什么 bug、解决了什么错误）

## 3. 遇到的技术难点
（提取遇到了什么技术问题，如 API 兼容、数据格式等）

## 4. 解决方案
（对应的解决方案是什么）

要求：
- 简洁，每项 1-2 句话
- 用 Markdown 格式
- 如果有代码改动，提及涉及的文件名
- 不要编造对话中没有的内容
- 如果某类内容缺失，写"无"

对话记录：
---
{conv_text}
---"""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    summary = response.choices[0].message.content or ""

    filepath = storage.save_report(f"project_{date}", summary)
    return f"项目总结已保存到 `{filepath}`\n\n{summary}"


def _load_devlog(date_str: str) -> str:
    """读取开发日志文件"""
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "devlog.md")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def import_devlog() -> str:
    """将 devlog.md 导入到今日对话记录中"""
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "devlog.md")
    if not os.path.exists(path):
        return "未找到 devlog.md，请在项目根目录创建该文件并写入开发日志。"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if not content.strip():
        return "devlog.md 为空，请先写入内容。"
    storage.append_conversation("user", f"[开发日志]\n{content}")
    return f"✅ 已导入开发日志（{len(content)} 字），说「项目总结」即可生成简报。"


# ---- 上传文件管理 ----

def list_uploaded_files() -> str:
    """列出所有上传的文件"""
    files = storage.list_uploads()
    if not files:
        return "暂无上传的文件。将 md/txt 文件放入 data/uploads/ 目录即可。"
    lines = [f"共 {len(files)} 个上传文件：", ""]
    for f in files:
        import os
        name = os.path.basename(f)
        size = os.path.getsize(f)
        lines.append(f"- `{name}` ({size} bytes)")
    return "\n".join(lines)


def import_uploaded_file(filename: str) -> str:
    """将指定的上传文件导入对话记录"""
    content = storage.read_upload(filename)
    if not content:
        return f"未找到文件 `{filename}`。说「查看上传文件」可列出所有可用文件。"
    storage.append_conversation("user", f"[上传文件: {filename}]\n{content}")
    return f"✅ 已导入 `{filename}`（{len(content)} 字），说「项目总结」即可生成简报。"


def add_job_application(company: str, position: str,
                        date: str = None, status: str = "已投递",
                        platform: str = "Boss直聘", notes: str = "") -> str:
    job = storage.add_application(
        company=company, position=position, date_str=date,
        status=status, platform=platform, notes=notes,
    )
    STATUS_MAP = {
        "沟通过":  "沟通过 💬",
        "已投递":  "已投递 📤",
        "面试":    "面试 🎤",
        "感兴趣":  "感兴趣 ⭐",
        "不合适":  "不合适 ❌",
    }
    st = STATUS_MAP.get(status, status)
    lines = [
        f"已记录 [{platform}] #{job['id']}：",
        f"  公司：{company}",
        f"  岗位：{position}",
        f"  状态：{st}",
        f"  日期：{job['date']}",
    ]
    if notes:
        lines.append(f"  备注：{notes}")
    return "\n".join(lines)


def list_job_applications(status: str = None, date: str = None) -> str:
    jobs = storage.list_applications(status=status, date_str=date)
    if not jobs:
        return "暂无投递记录。"
    total = len(jobs)
    by_status = {}
    for j in jobs:
        by_status.setdefault(j["status"], 0)
        by_status[j["status"]] += 1
    stats = " | ".join(f"{s} {c}家" for s, c in by_status.items())
    lines = [f"共投递 {total} 家公司（{stats}）：", ""]
    for j in jobs:
        line = f"  #{j['id']} [{j['date']}] {j['company']} — {j['position']} ({j['status']})"
        if j.get("notes"):
            line += f" | {j['notes']}"
        lines.append(line)
    return "\n".join(lines)


def update_job_status(application_id: int, new_status: str) -> str:
    job = storage.update_application_status(application_id, new_status)
    if not job:
        return f"未找到编号为 #{application_id} 的投递记录。"
    return f"已更新 #{application_id} {job['company']} — {job['position']} 状态为「{new_status}」"


# ---- Function Definitions ----

FUNCTION_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "generate_daily_report",
            "description": "生成某一天的日报：总结做了什么事、学了什么知识、遇到什么问题。日期不指定则生成今天的日报。",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "日期，格式 YYYY-MM-DD，默认今天",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_history",
            "description": "搜索历史对话记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "string",
                        "description": "搜索关键词，多个关键词用逗号分隔",
                    },
                },
                "required": ["keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_period",
            "description": "汇总一段时间的对话记录，生成阶段工作小结",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_job_application",
            "description": "记录一条投简历记录：在哪家公司投了什么岗位",
            "parameters": {
                "type": "object",
                "properties": {
                    "company": {"type": "string", "description": "公司名称"},
                    "position": {"type": "string", "description": "投递的岗位名称"},
                    "date": {"type": "string", "description": "投递日期 YYYY-MM-DD，默认今天"},
                    "status": {
                        "type": "string",
                        "description": "当前状态：沟通过=仅聊过、已投递=已发简历、面试=约面试、感兴趣=公司标记感兴趣、不合适=被拒或不合适",
                        "enum": ["沟通过", "已投递", "面试", "感兴趣", "不合适"],
                    },
                    "platform": {"type": "string", "description": "招聘平台，默认 Boss直聘"},
                    "notes": {"type": "string", "description": "备注，比如薪资范围、公司规模等"},
                },
                "required": ["company", "position"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_exported_files",
            "description": "列出所有历史导出的Boss直聘Excel文件。用户说「之前导出的文件」「历史记录」时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_push_project",
            "description": "将项目代码提交并推送到GitHub。用户说「推送GitHub」「更新仓库」「提交代码」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "commit 提交信息，如「修复Excel导出日期筛选」",
                    },
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_display_status",
            "description": "查看Git仓库当前状态（有哪些文件改动未提交）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_project_summary",
            "description": "根据今天的对话记录（含开发日志）生成项目开发简报（新增功能/修复问题/技术难点/解决方案），输出Markdown文件。用户说「项目总结」「开发简报」「今天做了什么」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "日期 YYYY-MM-DD，默认今天"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "import_devlog",
            "description": "导入项目根目录的 devlog.md 开发日志到对话记录中。用户说「导入开发日志」「导入devlog」时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_uploaded_files",
            "description": "列出 data/uploads/ 目录下所有上传的对话文件。用户说「查看上传文件」「有哪些上传的」时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "import_uploaded_file",
            "description": "将指定上传文件的内容导入今日对话记录。用户说「导入XX文件」「加载聊天记录」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "要导入的文件名，如 chat_with_gpt.md"},
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "boss_job_summary",
            "description": "统计汇总Boss直聘四个模块的投递数据（沟通过/已投递/面试/感兴趣数量），输出详细报告。用户说「投递汇总」「求职进度」「统计投递」时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_boss_excel",
            "description": "将Boss直聘投递记录导出为Excel表格文件。用户说「导出Excel」「生成表格」「导出投递记录」时调用。指定某天时说「导出2026-02-20的Excel」。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "按状态筛选导出：沟通过/已投递/面试/感兴趣，不传则导出全部",
                    },
                    "date": {
                        "type": "string",
                        "description": "导出指定日期的记录，格式YYYY-MM-DD，不传默认今天",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_job_status",
            "description": "更新某条投递记录的状态（比如从已投递改为面试）",
            "parameters": {
                "type": "object",
                "properties": {
                    "application_id": {"type": "integer", "description": "投递记录的编号（#数字）"},
                    "new_status": {
                        "type": "string",
                        "description": "新状态：沟通过/已投递/面试/感兴趣/不合适",
                        "enum": ["沟通过", "已投递", "面试", "感兴趣", "不合适"],
                    },
                },
                "required": ["application_id", "new_status"],
            },
        },
    },
]

SKILL_MAP = {
    "generate_daily_report": generate_daily_report,
    "search_history": search_history,
    "summarize_period": summarize_period,
    "fetch_boss_channels": fetch_boss_channels,
    "fetch_boss_applied": fetch_boss_applied,
    "fetch_boss_interviews": fetch_boss_interviews,
    "fetch_boss_interested": fetch_boss_interested,
    "boss_job_summary": boss_job_summary,
    "export_boss_excel": export_boss_excel,
    "list_exported_files": list_exported_files,
    "git_push_project": git_push_project,
    "git_display_status": git_display_status,
    "generate_project_summary": generate_project_summary,
    "import_devlog": import_devlog,
    "list_uploaded_files": list_uploaded_files,
    "import_uploaded_file": import_uploaded_file,
    "add_job_application": add_job_application,
    "list_job_applications": list_job_applications,
    "update_job_status": update_job_status,
}


def execute_skill(name: str, arguments: dict) -> str:
    fn = SKILL_MAP.get(name)
    if not fn:
        return f"未知技能: {name}"
    import inspect
    sig = inspect.signature(fn)
    valid = {k: v for k, v in arguments.items() if v is not None and k in sig.parameters}
    return fn(**valid)
