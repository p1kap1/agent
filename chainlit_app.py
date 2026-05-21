import chainlit as cl
from agent import WorkAgent


# ---- Python 3.14 + nest_asyncio compat ----
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
    await cl.Message(
        content="你好！我是 **FlowMate**，你的工作日志助手。\n\n"
        "新用户说「**开始设置**」配置模型/Key/Boss/GitHub。\n"
        "已配置好可以直接使用：\n\n"
        "📮 **求职管理**\n"
        "- 「同步投递」→ 拉取沟通过/已投递/面试/感兴趣\n"
        "- 「同步每日推荐」→ 每日职位推荐\n"
        "- 「投递汇总」→ 统计求职进度\n"
        "- 「导出Excel」→ 生成表格（支持日期筛选）\n\n"
        "📄 **日报总结**\n"
        "- 「生成日报」→ 投递+开发+技巧+知识推荐\n"
        "- 「项目总结」→ 开发简报\n"
        "- 「导入开发日志」→ 加载 devlog.md\n\n"
        "🔧 「搜索 XXX」「提交代码到 GitHub」「查看配置」\n\n"
        "开始吧！"
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    agent: WorkAgent = cl.user_session.get("agent")

    # 处理文件上传：保存到 data/uploads/
    if message.elements:
        for element in message.elements:
            if element.name and element.content:
                import os
                upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "uploads")
                os.makedirs(upload_dir, exist_ok=True)
                filepath = os.path.join(upload_dir, element.name)
                content = element.content.decode("utf-8") if isinstance(element.content, bytes) else str(element.content)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                await cl.Message(content=f"✅ 已保存 `{element.name}`，说「导入 {element.name}」即可加载内容。").send()
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
