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
    devlog_content = _load_devlog(date_str)
    uploads_content = _load_all_uploads()

    if not conversation and not applications and not devlog_content and not uploads_content:
        return f"{date_str} 没有对话记录、投递记录和开发日志，无法生成日报。"

    # ---- 构建上下文 ----
    context = []
    if conversation:
        for entry in conversation:
            role = "用户" if entry["role"] == "user" else "助手"
            context.append(f"[{entry['time'][:19]}] {role}: {entry['content']}")
    if devlog_content:
        context.append(f"\n[开发日志]\n{devlog_content}")
    if uploads_content:
        context.append(f"\n[上传文件]\n{uploads_content}")
    full_context = "\n".join(context)

    # 构建投递信息
    job_info = ""
    if applications:
        lines = []
        by_status = {}
        for j in applications:
            by_status.setdefault(j["status"], [])
            by_status[j["status"]].append(j)
        for status, jobs in by_status.items():
            lines.append(f"\n{status}（{len(jobs)}家）：")
            for j in jobs:
                parts = [j.get("company", ""), j.get("position", "")]
                if j.get("salary"): parts.append(j["salary"])
                if j.get("city"): parts.append(j["city"])
                lines.append(f"- {' · '.join(parts)}")
        job_info = "\n".join(lines)

    # ---- 一次性生成完整日报（减少API调用）----
    prompt = f"""以下是用户一天的活动记录。请生成一份完整的日报，包含以下四个部分：

## 1. 📮 今日投递
直接列出投递数据（已提供在下方）

## 2. 🎯 投递分析与建议
根据投递的岗位方向，分析用户的求职策略：
- 投递主要集中在哪些领域/技术栈
- 哪些技能在投递岗位中频繁出现，用户可能需要加强
- 给出 2-3 条具体的求职建议

## 3. 🛠 今日总结
- 如果有开发日志或上传文件，总结项目开发进展
- 如果是普通聊天，总结今天的工作学习内容
- 如果没有相关内容，写「今日无特别活动」

## 4. 📚 推荐学习知识
综合以下来源推荐 3-5 个用户最需要学习的知识点：
- 投递岗位要求的技能（从岗位名称和描述推断）
- 对话中提及但未深入的技术话题
- 上传文件/开发日志中的技术方向
- 每条包含：知识名称、一句话简介、为什么推荐

要求：Markdown 格式，简洁，不要编造。投递数据已提供在下方。

---
今日投递数据：
{job_info or '暂无投递'}

今日活动记录：
{full_context or '暂无活动记录'}
---"""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    report_body = response.choices[0].message.content or "日报生成失败，请重试。"

    # ---- 拼完整报告 ----
    day_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]
    full_report = (
        f"# 工作日报\n\n"
        f"**日期**: {date_str} {day_name}\n\n"
        f"---\n\n"
        f"{report_body}\n\n"
        f"---\n"
        f"*由 FlowMate 自动生成*"
    )

    filepath = storage.save_report(date_str, full_report)
    return f"日报已生成并保存到 `{filepath}`\n\n{full_report}"


def _load_all_uploads() -> str:
    """读取所有上传文件内容（支持 md/txt/json/log/py/csv/html/yaml/toml/pdf）"""
    files = storage.list_uploads()
    if not files:
        return ""
    parts = []
    supported = {".md", ".txt", ".json", ".log", ".py", ".csv", ".html", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".pdf"}
    for f in files:
        import os
        name = os.path.basename(f)
        ext = os.path.splitext(name)[1].lower()
        if ext not in supported:
            continue
        if ext == ".pdf":
            content = _read_pdf(f)
        else:
            content = storage.read_upload(name)
        if content:
            parts.append(f"### {name}\n```\n{content[:2000]}\n```")
    return "\n".join(parts)


def _read_pdf(filepath: str) -> str:
    """读取 PDF 文件内容"""
    try:
        import fitz
        doc = fitz.open(filepath)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text.strip()
    except Exception:
        return ""


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

# ---- 配置管理 ----

def _import_settings():
    import os, sys, importlib.util
    try:
        import settings
        return settings, None
    except ImportError:
        sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.py")
        spec = importlib.util.spec_from_file_location("settings", sp)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules["settings"] = mod
            spec.loader.exec_module(mod)
            return mod, None
        return None, "Settings 模块未找到"


def show_current_settings() -> str:
    """查看当前配置"""
    mod, err = _import_settings()
    if not mod:
        return err
    return mod.show_settings()


def run_setup_wizard() -> str:
    """新用户引导"""
    mod, err = _import_settings()
    if not mod:
        return err
    return mod.setup_wizard()


def select_ai_model(provider: str) -> str:
    """选择 AI 模型（deepseek/openai/zhipu/moonshot/custom）"""
    mod, err = _import_settings()
    if not mod:
        return err
    return mod.select_model(provider)


def set_user_api_key(key: str) -> str:
    """设置 API Key"""
    mod, err = _import_settings()
    if not mod:
        return err
    return mod.set_api_key(key)


def set_custom_model(name: str) -> str:
    """设置自定义模型名"""
    mod, err = _import_settings()
    if not mod:
        return err
    return mod.set_model_name(name)


def set_custom_api_url(url: str) -> str:
    """设置自定义 API 地址"""
    mod, err = _import_settings()
    if not mod:
        return err
    return mod.set_api_base_url(url)


def set_boss_user_cookie(cookie: str) -> str:
    """设置 Boss直聘 Cookie"""
    mod, err = _import_settings()
    if not mod:
        return err
    return mod.set_boss_cookie(cookie)


def set_github_access_token(token: str) -> str:
    """设置 GitHub Token"""
    mod, err = _import_settings()
    if not mod:
        return err
    return mod.set_github_token(token)


def switch_active_user(username: str) -> str:
    """切换或创建用户"""
    mod, err = _import_settings()
    if not mod:
        return err
    return mod.switch_user(username)


def dismiss_setup_reminder() -> str:
    """用户不需要配置引导，取消后续提醒"""
    mod, err = _import_settings()
    if not mod:
        return err
    return mod.dismiss_setup()


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


def fetch_daily_recommend() -> str:
    """获取 Boss直聘「每日推荐」列表"""
    boss, err = _import_boss()
    if not boss:
        return err
    try:
        jobs = boss.fetch_daily_recommend()
        n = boss._save_jobs_to_storage(jobs)
    except PermissionError as e:
        return f"⚠ Cookie 未配置或已过期：{e}"
    except Exception as e:
        return f"⚠ 获取每日推荐失败：{e}"
    return (
        f"✅ 每日推荐：获取成功，新增 {n} 条记录"
        if n > 0 else
        f"✅ 每日推荐：获取成功，数据已是最新（无新增）"
    )


# ---- 智联招聘 ----

def sync_zhaopin_all() -> str:
    """同步智联招聘全部（已投递+收藏+推荐）"""
    boss, err = _import_boss()
    if boss:
        try:
            import zhaopin
        except ImportError:
            import os, sys, importlib.util
            zp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zhaopin.py")
            spec = importlib.util.spec_from_file_location("zhaopin", zp)
            if spec and spec.loader:
                zhaopin = importlib.util.module_from_spec(spec)
                sys.modules["zhaopin"] = zhaopin
                spec.loader.exec_module(zhaopin)
            else:
                return "智联模块未找到"
        result = zhaopin.sync_zhaopin()
        lines = [f"智联同步完成：新增 {result['new']} 条"]
        for tab, count in result["counts"].items():
            lines.append(f"  {tab}: {count} 条")
        if result["errors"]:
            for e in result["errors"]:
                lines.append(f"  ⚠ {e}")
        return "\n".join(lines)
    return f"BOSS模块加载失败（{err}）"


def export_zhaopin_to_excel(date: str = None) -> str:
    """导出智联全部（投递+推荐）"""
    boss, err = _import_boss()
    if boss:
        try:
            import zhaopin
        except ImportError:
            import os, sys, importlib.util
            zp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zhaopin.py")
            spec = importlib.util.spec_from_file_location("zhaopin", zp)
            if spec and spec.loader:
                zhaopin = importlib.util.module_from_spec(spec)
                sys.modules["zhaopin"] = zhaopin
                spec.loader.exec_module(zhaopin)
            else:
                return "智联模块未找到"
        return zhaopin.export_zhaopin_excel(date_filter=date)
    return f"BOSS模块加载失败（{err}）"


def export_zhaopin_delivery_excel(date: str = None) -> str:
    """只导出智联投递（已投递+收藏）"""
    boss, err = _import_boss()
    if boss:
        try:
            import zhaopin
        except ImportError:
            import os, sys, importlib.util
            zp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zhaopin.py")
            spec = importlib.util.spec_from_file_location("zhaopin", zp)
            if spec and spec.loader:
                zhaopin = importlib.util.module_from_spec(spec)
                sys.modules["zhaopin"] = zhaopin
                spec.loader.exec_module(zhaopin)
            else:
                return "智联模块未找到"
        return zhaopin.export_zhaopin_delivery_excel(date_filter=date)
    return f"BOSS模块加载失败（{err}）"


def export_zhaopin_recommend_excel(date: str = None) -> str:
    """只导出智联推荐"""
    boss, err = _import_boss()
    if boss:
        try:
            import zhaopin
        except ImportError:
            import os, sys, importlib.util
            zp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zhaopin.py")
            spec = importlib.util.spec_from_file_location("zhaopin", zp)
            if spec and spec.loader:
                zhaopin = importlib.util.module_from_spec(spec)
                sys.modules["zhaopin"] = zhaopin
                spec.loader.exec_module(zhaopin)
            else:
                return "智联模块未找到"
        return zhaopin.export_zhaopin_recommend_excel(date_filter=date)
    return f"BOSS模块加载失败（{err}）"


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


def export_all_excel(date: str = None) -> str:
    """导出全部（投递 + 每日推荐）"""
    boss, err = _import_boss()
    if not boss:
        return err
    return boss.export_all_reports(date_filter=date)


def export_daily_recommend_excel(date: str = None) -> str:
    """单独导出每日推荐为 Excel"""
    boss, err = _import_boss()
    if not boss:
        return err
    return boss.export_daily_recommend_excel(date_filter=date)


def list_exported_files() -> str:
    """列出历史导出的 Excel 文件"""
    boss, err = _import_boss()
    if not boss:
        return err
    return boss.list_exports()


def show_daily_recommend_table() -> str:
    """展示每日推荐岗位表"""
    boss, err = _import_boss()
    if not boss:
        return err
    return boss.show_daily_recommend_table()


def show_application_table(status: str = None, date: str = None) -> str:
    """展示投递岗位表"""
    boss, err = _import_boss()
    if not boss:
        return err
    return boss.show_application_table(status=status, date_str=date)


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
            "name": "sync_all_applications",
            "description": "同步Boss直聘+智联招聘的投递数据（沟通过/已投递/面试/感兴趣/收藏），不含推荐。用户说「同步」「同步投递」「刷新」时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sync_all_recommends",
            "description": "同步Boss直聘+智联招聘的每日推荐数据。用户说「每日推荐」「同步推荐」时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sync_boss_applications",
            "description": "只同步Boss直聘的投递数据。用户说「同步Boss」「同步Boss直聘」时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sync_zhaopin_applications",
            "description": "只同步智联招聘的投递数据。用户说「同步智联」「智联招聘」时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_setup_wizard",
            "description": "新用户引导设置向导。用户说「开始设置」「不知道怎么用」「引导」时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_all_charts",
            "description": "一次性展示全部图表（投递趋势+状态分布+平台对比）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_web_search",
            "description": "搜索引擎查询最新资料。用户说「搜索XX最新资料」「帮我查一下XX」时调用。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "搜索关键词"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_refresh_liepin",
            "description": "生成刷新猎聘Cookie的脚本，用于解决猎聘登录态过期问题。用户说「刷新猎聘」「猎聘过期了」时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_ai_model",
            "description": "选择AI模型厂商。用户说「选择模型」「用DeepSeek」「用OpenAI」「用智谱」「用自定义模型」时调用。",
            "parameters": {
                "type": "object",
                "properties": {"provider": {"type": "string", "description": "deepseek/openai/zhipu/moonshot/custom"}},
                "required": ["provider"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_user_api_key",
            "description": "设置API Key。用户说「设置Key为xxx」时调用。",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string", "description": "API Key"}},
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_custom_model",
            "description": "设置自定义模型名称。用户选自定义模型后用。",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "模型名称"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_custom_api_url",
            "description": "设置自定义API地址。用户选自定义模型后用。",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "API Base URL"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_boss_user_cookie",
            "description": "设置Boss直聘Cookie。用户说「更新Boss Cookie」时调用。",
            "parameters": {
                "type": "object",
                "properties": {"cookie": {"type": "string", "description": "完整Cookie字符串"}},
                "required": ["cookie"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_github_access_token",
            "description": "设置GitHub Token并配置git remote。用户说「设置GitHub Token」时调用。",
            "parameters": {
                "type": "object",
                "properties": {"token": {"type": "string", "description": "GitHub Token"}},
                "required": ["token"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "switch_active_user",
            "description": "切换或创建用户。用户说「切换用户」「换账号」时调用。",
            "parameters": {
                "type": "object",
                "properties": {"username": {"type": "string", "description": "用户名"}},
                "required": ["username"],
            },
        },
    },
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
            "name": "fetch_boss_interested",
            "description": "从Boss直聘获取「感兴趣」列表。用户说「同步感兴趣」时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_daily_recommend",
            "description": "从Boss直聘获取「每日推荐」职位列表。用户说「同步每日推荐」「每日推荐」时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sync_zhaopin_all",
            "description": "同步智联招聘的已投递、我的收藏、职位推荐数据。用户说「同步智联」「智联招聘」时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_zhaopin_to_excel",
            "description": "导出智联招聘投递记录为Excel文件。用户说「导出智联Excel」「智联表格」时调用。",
            "parameters": {
                "type": "object",
                "properties": {"date": {"type": "string", "description": "日期 YYYY-MM-DD，默认今天"}},
            },
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
            "name": "export_all_excel",
            "description": "导出全部数据（投递+每日推荐）为Excel文件。用户说「导出Excel」「导出全部」时调用。",
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
            "name": "export_boss_excel",
            "description": "将投递记录（沟通过/已投递/面试/感兴趣）导出为Excel。用户说「导出Excel」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "按状态筛选"},
                    "date": {"type": "string", "description": "日期 YYYY-MM-DD，默认今天"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_daily_recommend_excel",
            "description": "单独导出每日推荐岗位为Excel文件。用户说「导出每日推荐」「每日推荐Excel」时调用。",
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
            "name": "show_daily_recommend_table",
            "description": "以表格形式展示今天的每日推荐岗位。用户说「每日推荐表」「展示每日推荐」「推荐岗位」时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_application_table",
            "description": "以表格形式展示投递岗位（沟通过/已投递/面试/感兴趣）。用户说「投递表」「岗位表」「展示投递」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "按状态筛选"},
                    "date": {"type": "string", "description": "日期 YYYY-MM-DD，默认今天"},
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


# ---- 统一同步（跨平台）----

def sync_all_applications() -> str:
    """同步全部平台的投递数据（Boss + 智联 + 猎聘，不含推荐）"""
    parts = [sync_boss_applications(), sync_zhaopin_applications()]
    try:
        parts.append(sync_liepin_applications())
    except Exception as e:
        parts.append(f"猎聘: ⚠ {e}")
    return "\n".join(parts)


def sync_all_recommends() -> str:
    """同步全部平台的每日推荐（Boss + 智联 + 猎聘）"""
    parts = [sync_boss_recommends(), sync_zhaopin_recommends()]
    try:
        parts.append(sync_liepin_recommends())
    except Exception as e:
        parts.append(f"猎聘推荐: ⚠ {e}")
    return "\n".join(parts)


def sync_boss_applications() -> str:
    """只同步 Boss直聘 投递数据"""
    boss, err = _import_boss()
    if not boss:
        return f"Boss模块: {err}"
    lines = ["Boss直聘今日投递："]
    total = 0
    for tab, fetcher in [
        ("沟通过", boss.fetch_boss_channels),
        ("已投递", boss.fetch_boss_applied),
        ("面试", boss.fetch_boss_interviews),
        ("感兴趣", boss.fetch_boss_interested),
    ]:
        try:
            jobs = fetcher()
            n = boss._save_jobs_to_storage(jobs)
            total += n
            lines.append(f"  {tab}: {len(jobs)}条 → 新增{n}条")
        except Exception as e:
            lines.append(f"  {tab}: ⚠ {e}")
    lines.append(f"\n今日共新增 {total} 条投递记录")
    return "\n".join(lines)


def sync_boss_recommends() -> str:
    """只同步 Boss直聘 每日推荐"""
    boss, err = _import_boss()
    if not boss:
        return f"Boss模块: {err}"
    try:
        jobs = boss.fetch_daily_recommend()
        n = boss._save_jobs_to_storage(jobs)
        return f"Boss每日推荐: {len(jobs)}条 → 新增{n}条"
    except Exception as e:
        return f"Boss每日推荐: ⚠ {e}"


def sync_zhaopin_applications() -> str:
    """只同步 智联招聘 投递数据"""
    try:
        import zhaopin as _zp
    except ImportError:
        import os, sys, importlib.util
        zp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zhaopin.py")
        spec = importlib.util.spec_from_file_location("zhaopin", zp)
        _zp = importlib.util.module_from_spec(spec)
        sys.modules["zhaopin"] = _zp
        spec.loader.exec_module(_zp)

    lines = ["智联招聘今日投递："]
    total = 0
    for tab, fetcher in [
        ("已投递", _zp.fetch_zhaopin_applied),
        ("收藏", _zp.fetch_zhaopin_collect),
    ]:
        try:
            jobs = fetcher()
            n = _zp._save_to_storage(jobs)
            total += n
            lines.append(f"  {tab}: {len(jobs)}条 → 新增{n}条")
        except Exception as e:
            lines.append(f"  {tab}: ⚠ {e}")
    lines.append(f"\n今日共新增 {total} 条投递记录")
    return "\n".join(lines)


def sync_zhaopin_recommends() -> str:
    """只同步 智联招聘 推荐"""
    try:
        import zhaopin as _zp2
    except ImportError:
        import os, sys, importlib.util
        zp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zhaopin.py")
        spec = importlib.util.spec_from_file_location("zhaopin", zp)
        _zp2 = importlib.util.module_from_spec(spec)
        sys.modules["zhaopin"] = _zp2
        spec.loader.exec_module(_zp2)

    try:
        jobs = _zp2.fetch_zhaopin_recommend()
        n = _zp2._save_to_storage(jobs)
        return f"智联推荐: API返回{len(jobs)}条 → 新增{n}条"
    except Exception as e:
        return f"智联推荐: ⚠ {e}"


# ---- 猎聘 ----

def _import_liepin():
    import os, sys, importlib.util
    try:
        import liepin
        return liepin, None
    except ImportError:
        lp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "liepin.py")
        spec = importlib.util.spec_from_file_location("liepin", lp)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules["liepin"] = mod
            spec.loader.exec_module(mod)
            return mod, None
        return None, f"猎聘模块未找到: {lp}"


def sync_liepin_applications() -> str:
    """同步猎聘投递数据"""
    lp, err = _import_liepin()
    if not lp:
        return err
    lines = ["猎聘今日投递："]
    total = 0
    for tab, fetcher in [
        ("已投递", lp.fetch_liepin_applied),
        ("已查看", lp.fetch_liepin_viewed),
        ("面试", lp.fetch_liepin_interview),
        ("收藏", lp.fetch_liepin_collect),
    ]:
        try:
            jobs = fetcher()
            n = lp._save_to_storage(jobs)
            total += n
            lines.append(f"  {tab}: {len(jobs)}条 → 新增{n}条")
        except Exception as e:
            lines.append(f"  {tab}: ⚠ {e}")
    lines.append(f"\n今日共新增 {total} 条")
    return "\n".join(lines)


def sync_liepin_recommends() -> str:
    """同步猎聘推荐"""
    lp, err = _import_liepin()
    if not lp:
        return err
    try:
        jobs = lp.fetch_liepin_recommend()
        n = lp._save_to_storage(jobs)
        return f"猎聘推荐: {len(jobs)}条 → 新增{n}条"
    except Exception as e:
        return f"猎聘推荐: ⚠ {e}"


def export_liepin_to_excel(date: str = None) -> str:
    """导出猎聘全部"""
    lp, err = _import_liepin()
    if not lp:
        return err
    return lp.export_liepin_excel(date_filter=date)


def export_liepin_delivery_to_excel(date: str = None) -> str:
    """只导出猎聘投递"""
    lp, err = _import_liepin()
    if not lp:
        return err
    return lp.export_liepin_delivery_excel(date_filter=date)


def export_liepin_recommend_to_excel(date: str = None) -> str:
    """只导出猎聘推荐"""
    lp, err = _import_liepin()
    if not lp:
        return err
    return lp.export_liepin_recommend_excel(date_filter=date)


# ---- 数据可视化 ----

def show_daily_trend(days: int = 14) -> str:
    from charts import chart_daily_trend
    return chart_daily_trend(days)


def show_status_pie() -> str:
    from charts import chart_status_pie
    return chart_status_pie()


def show_platform_compare() -> str:
    from charts import chart_platform_compare
    return chart_platform_compare()


def show_all_charts() -> str:
    from charts import chart_all
    return chart_all()


# ---- 外部工具（MCP 风格）----

def skill_web_search(query: str) -> str:
    """网页搜索"""
    try:
        import tools
    except ImportError:
        return "工具模块未安装。"
    return tools.web_search(query)


def skill_refresh_liepin() -> str:
    """刷新猎聘 Cookie"""
    try:
        import tools
    except ImportError:
        return "工具模块未安装。"
    return tools.refresh_liepin_cookie()


def export_all_delivery(date: str = None) -> str:
    """导出全部平台投递（不含推荐）"""
    from boss import export_excel as boss_delivery
    results = [
        boss_delivery(date_filter=date),
        export_zhaopin_delivery_excel(date=date),
        export_liepin_delivery_to_excel(date=date),
    ]
    return "\n".join(results)


def export_all_recommends_excel(date: str = None) -> str:
    """导出全部平台推荐（不含投递）"""
    from boss import export_daily_recommend_excel as boss_rec
    results = [
        boss_rec(date_filter=date),
        export_zhaopin_recommend_excel(date=date),
        export_liepin_recommend_to_excel(date=date),
    ]
    return "\n".join(results)


def export_boss_recommend_excel(date: str = None) -> str:
    """只导出Boss推荐"""
    from boss import export_daily_recommend_excel as boss_rec
    return boss_rec(date_filter=date)


SKILL_MAP = {
    "sync_all_applications": sync_all_applications,
    "sync_all_recommends": sync_all_recommends,
    "sync_boss_applications": sync_boss_applications,
    "sync_boss_recommends": sync_boss_recommends,
    "sync_zhaopin_applications": sync_zhaopin_applications,
    "sync_zhaopin_recommends": sync_zhaopin_recommends,
    "sync_liepin_applications": sync_liepin_applications,
    "sync_liepin_recommends": sync_liepin_recommends,
    "export_liepin_to_excel": export_liepin_to_excel,
    "export_liepin_delivery_to_excel": export_liepin_delivery_to_excel,
    "export_liepin_recommend_to_excel": export_liepin_recommend_to_excel,
    "export_all_delivery": export_all_delivery,
    "export_all_recommends_excel": export_all_recommends_excel,
    "export_boss_recommend_excel": export_boss_recommend_excel,
    "export_zhaopin_delivery_excel": export_zhaopin_delivery_excel,
    "export_zhaopin_recommend_excel": export_zhaopin_recommend_excel,
    "show_daily_trend": show_daily_trend,
    "show_status_pie": show_status_pie,
    "show_platform_compare": show_platform_compare,
    "show_all_charts": show_all_charts,
    "skill_web_search": skill_web_search,
    "skill_refresh_liepin": skill_refresh_liepin,
    "run_setup_wizard": run_setup_wizard,
    "show_current_settings": show_current_settings,
    "select_ai_model": select_ai_model,
    "set_user_api_key": set_user_api_key,
    "set_custom_model": set_custom_model,
    "set_custom_api_url": set_custom_api_url,
    "set_boss_user_cookie": set_boss_user_cookie,
    "set_github_access_token": set_github_access_token,
    "switch_active_user": switch_active_user,
    "dismiss_setup_reminder": dismiss_setup_reminder,
    "generate_daily_report": generate_daily_report,
    "search_history": search_history,
    "summarize_period": summarize_period,
    "fetch_boss_channels": fetch_boss_channels,
    "fetch_boss_applied": fetch_boss_applied,
    "fetch_boss_interviews": fetch_boss_interviews,
    "fetch_boss_interested": fetch_boss_interested,
    "fetch_daily_recommend": fetch_daily_recommend,
    "sync_zhaopin_all": sync_zhaopin_all,
    "export_zhaopin_to_excel": export_zhaopin_to_excel,
    "boss_job_summary": boss_job_summary,
    "export_boss_excel": export_boss_excel,
    "export_all_excel": export_all_excel,
    "export_daily_recommend_excel": export_daily_recommend_excel,
    "list_exported_files": list_exported_files,
    "show_daily_recommend_table": show_daily_recommend_table,
    "show_application_table": show_application_table,
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
