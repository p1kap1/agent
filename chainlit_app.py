import chainlit as cl
from agent import WorkAgent
import json
import os

# ---- 聊天记录本地持久化 ----
CHAT_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "chat_history.json")


def _save_chat_history():
    """保存当前对话到 JSON 文件"""
    try:
        history = cl.user_session.get("chat_history", [])
        if history:
            os.makedirs(os.path.dirname(CHAT_HISTORY_FILE), exist_ok=True)
            with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history[-100:], f, ensure_ascii=False)  # 最多保留100条
    except Exception:
        pass


def _load_chat_history() -> list:
    """从 JSON 文件恢复对话"""
    if os.path.exists(CHAT_HISTORY_FILE):
        try:
            with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []
# nest_asyncio._run_once pops the current task before executing callbacks,
# causing asyncio.current_task() to return None. This breaks:
# 1. anyio._core._eventloop.current_async_library() → NoEventLoopError
# 2. anyio._backends._asyncio.CancelScope.__enter__ → TypeError
# 3. asyncio.timeouts.Timeout.__aenter__ → RuntimeError
# 4. engineio.async_server._service_task → RuntimeError

import asyncio as _asyncio
import threading as _threading
import heapq as _heapq

_nest_task = _threading.local()

# ---- Patch 1: Store popped task in thread-local during _run_once ----

def _patch_run_once(loop):
    if getattr(loop, "_nest14_patched", False):
        return

    _orig = loop._run_once

    def _new_run_once(self):
        cur = _asyncio.tasks._current_tasks
        ready = self._ready
        sched = self._scheduled
        while sched and sched[0]._cancelled:
            _heapq.heappop(sched)
        timeout = (
            0 if ready or self._stopping
            else min(max(sched[0]._when - self.time(), 0), 86400)
            if sched else None
        )
        ev = self._selector.select(timeout)
        self._process_events(ev)
        et = self.time() + self._clock_resolution
        while sched and sched[0]._when < et:
            ready.append(_heapq.heappop(sched))
        for _ in range(len(ready)):
            if not ready:
                break
            h = ready.popleft()
            if not h._cancelled:
                t = cur.pop(self, None)
                _nest_task.value = t
                try:
                    h._run()
                finally:
                    if t is not None:
                        cur[self] = t
                    _nest_task.value = None

    loop._run_once = _new_run_once.__get__(loop, type(loop))
    loop._nest14_patched = True

_patch_run_once(_asyncio.get_event_loop())

# ---- Patch 2: current_task never returns None when loop is running ----

_orig_current_task = _asyncio.current_task

def _patched_current_task(loop=None):
    t = _orig_current_task(loop)
    if t is not None:
        return t
    t = getattr(_nest_task, "value", None)
    if t is not None:
        return t
    if loop is None:
        try:
            loop = _asyncio.get_running_loop()
        except RuntimeError:
            return None
    return _asyncio.tasks._current_tasks.get(loop)

_asyncio.current_task = _patched_current_task

import anyio._backends._asyncio as _aba
_aba.current_task = _patched_current_task

# ---- Patch 3: current_async_library fallback ----

import anyio._core._eventloop as _aloop
_orig_alib = _aloop.current_async_library

def _patched_current_async_library():
    r = _orig_alib()
    if r is None:
        try:
            if _asyncio.get_running_loop() is not None:
                return "asyncio"
        except RuntimeError:
            pass
    return r

_aloop.current_async_library = _patched_current_async_library

# ---- Patch 4: CancelScope.__enter__ handles None host_task ----

_orig_cs_enter = _aba.CancelScope.__enter__

def _patched_enter(self):
    if self._active:
        raise RuntimeError(
            "Each CancelScope may only be used for a single 'with' block")
    import anyio._backends._asyncio as _m
    host = _patched_current_task()
    if host is None:
        host = _asyncio.tasks._CTask()  # dummy fallback
    self._host_task = host
    self._tasks.add(host)
    try:
        ts = _m._task_states[host]
    except KeyError:
        ts = _m.TaskState(None, self)
        _m._task_states[host] = ts
    else:
        self._parent_scope = ts.cancel_scope
        ts.cancel_scope = self
        if self._parent_scope is not None:
            self._parent_scope._child_scopes.add(self)
            self._parent_scope._tasks.discard(host)
    self._timeout()
    self._active = True
    if self._cancel_called:
        self._deliver_cancellation(self)
    return self

_aba.CancelScope.__enter__ = _patched_enter

# ---- Patch 5: Timeout.__aenter__ handles None current_task ----

import asyncio.timeouts as _ato
_orig_timeout_enter = _ato.Timeout.__aenter__

async def _patched_timeout_enter(self):
    if self._state is not _ato._State.CREATED:
        raise RuntimeError("Timeout has already been entered")
    task = _patched_current_task()
    if task is None:
        # nest_asyncio popped it; try original one more time
        task = _asyncio.tasks._CTask()
    self._state = _ato._State.ENTERED
    self._task = task
    self._cancelling = task.cancelling()
    self.reschedule(self._when)
    return self

_ato.Timeout.__aenter__ = _patched_timeout_enter
# -------------------------------------------------


@cl.on_chat_start
async def start():
    cl.user_session.set("agent", WorkAgent())

    try:
        from settings import needs_setup
        if needs_setup():
            cl.user_session.set("setup_mode", True)
            await cl.Message(
                content="👋 欢迎使用 **FlowMate**！检测到你还未配置 AI 模型。\n\n"
                "请选择模型：\n"
                "- 「**用DeepSeek**」（推荐，国产免费额度）\n"
                "- 「**用OpenAI**」\n"
                "- 「**用智谱**」\n\n"
                "然后「**设置Key为sk-xxx**」填入你的 API Key。\n"
                "暂时不想配说「**跳过**」。"
            ).send()
            return
    except Exception:
        pass

    cl.user_session.set("setup_mode", False)

    # 新会话：清空对话历史
    cl.user_session.set("chat_history", [])

    await cl.Message(
        content="嗨～我是 **FlowMate**，你的专属工作伴侣 💼\n\n"
        "我能帮你打理这些事：\n\n"
        "📮 **求职管家**\n"
        "「同步投递」·「同步推荐」·「投递汇总」·「导出Excel」·「图表」\n"
        "→ Boss直聘 + 智联 + 猎聘 三平台一站式管理\n\n"
        "📝 **日报助手**\n"
        "「生成日报」→ 投递分析 + 学习建议 + 技能推荐\n"
        "「项目总结」·「导入开发日志」·「搜索历史」\n\n"
        "🔧 **工具箱**\n"
        "「查看配置」·「提交到GitHub」·「切换用户」·「开始设置」\n\n"
        "拖一个文件进来，我能读你的简历、JD、聊天记录哦 📎\n\n"
        "今天想从哪儿开始？😊"
    ).send()


@cl.on_chat_resume
async def resume(thread: dict):
    """刷新页面恢复历史"""
    history = _load_chat_history()
    if history:
        for msg in history[-20:]:
            await cl.Message(author=msg.get("author"), content=msg.get("content", "")).send()
        await cl.Message(content=f"👋 欢迎回来！上次 {len(history)} 条记录已恢复。说「帮助」查看功能。").send()
    else:
        await cl.Message(content=f"👋 欢迎回来！说「帮助」查看功能列表。").send()


@cl.on_chat_resume
async def resume(thread: dict):
    """用户刷新页面，恢复历史记录"""
    await cl.Message(
        content=f"👋 欢迎回来！上次对话还在，继续聊吧～\n"
        f"说「帮助」可以随时查看功能列表。"
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    agent: WorkAgent = cl.user_session.get("agent")
    msg = message.content.strip()

    # 功能介绍 / 帮助：直接回复，不需 AI
    if any(w in msg for w in ["你能做什么", "功能介绍", "有什么功能", "怎么用", "帮助", "help", "使用指南", "全部功能"]):
        await cl.Message(
            content="💼 **FlowMate 能帮你做这些**：\n\n"
            "📮 **求职管家**\n"
            "「同步投递」Boss+智联+猎聘 ·「同步推荐」·「投递汇总」\n"
            "「导出Excel」·「投递表」·「每日推荐表」·「图表」\n\n"
            "📝 **日报助手**\n"
            "「生成日报」投递分析+学习建议+技能推荐\n"
            "「项目总结」·「搜索XX最新资料」（实时搜索引擎）\n\n"
            "📁 **文件上传**\n"
            "拖 md/pdf/txt/json/log 到对话框 → 自动分析\n\n"
            "🔧 **工具箱**\n"
            "「查看配置」·「提交到GitHub」·「切换用户」·「刷新猎聘」\n\n"
            "📊 **多平台**\n"
            "Boss直聘 · 智联招聘 · 猎聘 | 支持 DeepSeek/OpenAI/智谱\n\n"
            "今天想从哪儿开始？😊"
        ).send()
        return

    # 配置模式：本地处理设置命令，不经过 AI
    if cl.user_session.get("setup_mode"):
        msg = message.content.strip()
        try:
            reply = _handle_setup_command(msg)
            if reply:
                await cl.Message(content=reply).send()
                # 检查是否配置完成
                from settings import needs_setup
                if not needs_setup():
                    cl.user_session.set("setup_mode", False)
                    await cl.Message(
                        content="✅ 配置完成！现在可以使用了。\n\n"
                        "「同步投递」「生成日报」「导出Excel」等等，开始吧！"
                    ).send()
                return
        except Exception as e:
            await cl.Message(content=f"配置失败: {e}").send()
            return

    # 文件上传处理
    if message.elements:
        import os, re, time, uuid
        upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "uploads")
        os.makedirs(upload_dir, exist_ok=True)

        for element in message.elements:
            if not element.name:
                continue

            content = None
            # 优先从 content 读取，失败则从 path 读取
            try:
                content = element.content
            except Exception:
                pass

            if content is None and hasattr(element, "path") and element.path and os.path.exists(element.path):
                try:
                    with open(element.path, "rb") as f:
                        content = f.read()
                except Exception:
                    pass

            if content is None:
                await cl.Message(content=f"⚠ `{element.name}` 内容为空或读取失败").send()
                continue
                await cl.Message(content=f"⚠ `{element.name}` 读取失败").send()
                continue

            # 安全文件名
            name = os.path.basename(element.name)
            name = re.sub(r'[^\w\.\-]', '_', name)
            base, ext = os.path.splitext(name)
            ext = ext.lower()
            if len(base) > 40:
                base = base[:40]
            safe_name = f"{base}_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"

            allowed = {".md", ".txt", ".json", ".log", ".py", ".csv", ".html", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".pdf"}
            if ext not in allowed:
                await cl.Message(content=f"⚠ 不支持 `{ext}`，支持: {', '.join(sorted(allowed))}").send()
                continue

            filepath = os.path.join(upload_dir, safe_name)
            try:
                if isinstance(content, bytes):
                    with open(filepath, "wb") as f:
                        f.write(content)
                else:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(str(content))
            except Exception as e:
                await cl.Message(content=f"❌ 保存失败: {e}").send()
                continue

            chars = len(content)
            await cl.Message(
                content=f"📎 已保存 `{element.name}` ({chars:,} 字符)\n"
                f"说「生成日报」即可将其纳入分析。"
            ).send()
        return

    try:
        reply = agent.chat(message.content)
    except Exception as e:
        import traceback
        reply = f"❌ 内部错误: {e}\n```\n{traceback.format_exc()}\n```"
    
    import os
    debug_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "debug.log")
    debug_info = ""
    if os.path.exists(debug_log):
        with open(debug_log, "r", encoding="utf-8") as f:
            lines = f.readlines()
        recent = [l for l in lines if "CALL" in l or "RESULT" in l]
        if recent:
            debug_info = "\n\n--- 🔍 技能调用详情 ---\n" + "".join(recent[-8:])
        os.remove(debug_log)
    
    await cl.Message(content=reply + debug_info).send()

    # 保存对话历史
    history = cl.user_session.get("chat_history", [])
    history.append({"author": "用户", "content": msg})
    history.append({"author": "FlowMate", "content": reply})
    cl.user_session.set("chat_history", history)
    _save_chat_history()


def _handle_setup_command(msg: str) -> str | None:
    """本地处理设置命令，不依赖 AI"""
    import re
    from settings import (
        select_model, set_api_key, set_model_name, set_api_base_url,
        set_boss_cookie, set_github_token, switch_user, dismiss_setup,
        MODEL_PRESETS,
    )
    msg_lower = msg.lower()

    # 跳过
    if any(w in msg_lower for w in ["跳过", "不需要", "不用", "暂不", "skip"]):
        return dismiss_setup()

    # 模型选择
    for key, preset in MODEL_PRESETS.items():
        if key != "custom" and key in msg_lower:
            return select_model(key)

    if "自定义" in msg or "custom" in msg_lower:
        return select_model("custom")

    # API Key
    if "设置key" in msg_lower or "设置 key" in msg_lower or "apikey" in msg_lower or "api key" in msg_lower:
        # 提取 key: 设置Key为sk-xxx 或 设置key为 sk-xxx
        import re
        m = re.search(r'(?:sk-|SK-)\S+', msg)
        if m:
            return set_api_key(m.group(0))
        parts = msg.replace("：", ":").split("为", 1)
        if len(parts) > 1:
            return set_api_key(parts[1].strip())
        return "请用「设置Key为sk-xxx」格式。例如：设置Key为sk-abc123"

    # 模型名
    if "设置模型" in msg or "模型名" in msg:
        parts = msg.replace("：", ":").split("为", 1)
        return set_model_name(parts[1].strip()) if len(parts) > 1 else "请用「设置模型为gpt-4」格式"

    # API 地址
    if "设置api" in msg_lower or "api地址" in msg_lower or "api 地址" in msg_lower:
        parts = msg.replace("：", ":").split("为", 1)
        return set_api_base_url(parts[1].strip()) if len(parts) > 1 else "请用「设置API地址为https://xxx」格式"

    # Boss Cookie
    if "cookie" in msg_lower and "boss" in msg_lower:
        parts = msg.replace("：", ":").split(":", 1)
        return set_boss_cookie(parts[1].strip()) if len(parts) > 1 else "请提供完整 Cookie 字符串"

    # GitHub Token
    if "token" in msg_lower or "github" in msg_lower:
        m = re.search(r'(?:ghp_|github_pat_)\S+', msg)
        if m:
            return set_github_token(m.group(0))
        parts = msg.replace("：", ":").split("为", 1)
        return set_github_token(parts[1].strip()) if len(parts) > 1 else "请用「设置GitHub Token为ghp_xxx」格式"

    # 切换用户
    if "切换用户" in msg or "换账号" in msg:
        parts = msg.replace("：", ":").split("用户", 1)
        if len(parts) > 1:
            return switch_user(parts[1].strip())
        return "请用「切换用户 用户名」格式"

    return None
