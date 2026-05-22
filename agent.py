import json
import os
from datetime import date, datetime

from config import client, OPENAI_MODEL
from skills import FUNCTION_DEFINITIONS, execute_skill
import storage

DEBUG_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "debug.log")
RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.md")
MAX_CONTEXT_CHARS = 200000  # 约 100K tokens，DeepSeek 128K，给响应留余量
KEEP_RECENT = 10  # 至少保留最近 N 轮对话


def _debug(msg: str):
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {msg}\n")


def _load_system_prompt() -> str:
    """从 rules.md 热加载系统提示，{{today}} 替换为当前日期"""
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = "你是 FlowMate，一个工作日志助手。今天的日期是 {{today}}。"
    return content.replace("{{today}}", date.today().isoformat())


def _count_chars(messages: list[dict]) -> int:
    return sum(len(m.get("content", "")) for m in messages)


def _compress_history(agent) -> None:
    """压缩历史：保留系统提示 + 最近 KEEP_RECENT 轮，其余总结为记忆"""
    msgs = agent.messages
    if _count_chars(msgs) < MAX_CONTEXT_CHARS:
        return

    # 分离系统提示 + 最近轮次
    system_msg = msgs[0]
    recent = msgs[-KEEP_RECENT * 2:]
    old_messages = msgs[1:-KEEP_RECENT * 2]

    if not old_messages:
        return

    # 把旧消息喂给 AI 生成摘要
    summary_prompt = "请用一两句话概括以下对话历史中的关键信息。只说要点，不要废话。\n\n"
    for m in old_messages[-20:]:  # 最多取20条旧消息做摘要
        role = m.get("role", "?")
        if role == "tool":
            summary_prompt += f"[工具结果]: {m.get('content', '')[:200]}\n"
        elif role in ("user", "assistant"):
            who = "用户" if role == "user" else "助手"
            summary_prompt += f"[{who}]: {m.get('content', '')[:300]}\n"

    try:
        summary_resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": summary_prompt}],
            max_tokens=200,
        )
        memory = summary_resp.choices[0].message.content or ""
    except Exception:
        memory = "（对话历史已压缩）"

    # 重建消息：系统提示 + 记忆 + 最近轮次
    memory_context = f"[历史记忆] {memory}\n\n今天的日期是 {date.today().isoformat()}。"

    agent.messages = [
        {"role": "system", "content": _load_system_prompt()},
        {"role": "user", "content": memory_context},
        {"role": "assistant", "content": "好的，已了解之前的对话背景。"},
    ] + recent

    _debug(f"Memory compressed: {len(msgs) - len(agent.messages)} messages → summary")


class WorkAgent:
    def __init__(self):
        self.messages = [{"role": "system", "content": _load_system_prompt()}]

    def chat(self, user_message: str) -> str:
        storage.append_conversation("user", user_message)
        self.messages.append({"role": "user", "content": user_message})

        # 自动压缩
        _compress_history(self)

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=self.messages,
            tools=FUNCTION_DEFINITIONS,
            tool_choice="auto",
        )

        msg = response.choices[0].message

        if msg.tool_calls:
            self.messages.append(msg)

            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                _debug(f"CALL {name}({json.dumps(args, ensure_ascii=False)})")
                result = execute_skill(name, args)
                _debug(f"RESULT {name}: {result[:200]}")
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

            final_response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=self.messages,
            )
            final_msg = final_response.choices[0].message
            self.messages.append(final_msg)
            reply = final_msg.content or ""
            storage.append_conversation("assistant", reply)
            return reply

        reply = msg.content or ""
        self.messages.append(msg)
        storage.append_conversation("assistant", reply)
        return reply

    def reset(self):
        self.messages = [{"role": "system", "content": _load_system_prompt()}]
