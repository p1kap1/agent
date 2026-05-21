import json
import os
from datetime import date, datetime

from config import client, OPENAI_MODEL
from skills import FUNCTION_DEFINITIONS, execute_skill
import storage

DEBUG_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "debug.log")


def _debug(msg: str):
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {msg}\n")

SYSTEM_PROMPT = f"""你是 FlowMate，一个工作日志助手。今天的日期是 {date.today().isoformat()}。

你的任务是：
1. 和用户自然聊天，帮助他们梳理思路、解答问题
2. 自动记录所有对话
3. 帮用户记录和管理投简历进度
4. 当用户要求时，生成日报、搜索历史、做阶段总结

你可以调用的功能：
- generate_daily_report: 生成日报
- search_history / summarize_period: 搜索和阶段总结
- fetch_boss_channels: 同步「沟通过」列表
- fetch_boss_applied: 同步「已投递」列表
- fetch_boss_interviews: 同步「面试」列表
- fetch_boss_interested: 同步「感兴趣」列表
- boss_job_summary: 汇总四个模块的投递统计
- add_job_application / list_job_applications / update_job_status: 手动记录/查看/更新

触发规则：
- 用户说"同步"、"刷新投递"、"更新" → 依次调用 fetch_boss_channels + fetch_boss_applied + fetch_boss_interviews + fetch_boss_interested
- 用户说"每日推荐"、"同步推荐" → fetch_daily_recommend
- 用户说"投递汇总"、"求职进度"、"统计" → boss_job_summary
- 用户说"看看投了多少"、"投递情况" → list_job_applications
- 用户说"投了XX"、"沟通了XX" → add_job_application（公司、岗位从用户消息中提取）
- 用户说"XX约面试了"、"进面试了" → update_job_status(new_status="面试")
- 用户说"日报"、"今天总结" → generate_daily_report
- 用户说"搜索"、"找一下" → search_history
- 用户说"本周小结"、"阶段总结" → summarize_period
- 用户说"导出"、"生成Excel"、"导出投递记录" → export_boss_excel
- 用户说"之前的文件"、"历史导出"、"以前的数据" → list_exported_files
- 用户说"推送GitHub"、"提交代码"、"更新仓库" → git_push_project
- 用户说"Git状态"、"看看改了什么" → git_display_status
- 用户说"项目总结"、"开发简报"、"今天干了什么" → generate_project_summary

其他时间就像普通助手一样聊天。回复请使用中文，简洁友好。"""


class WorkAgent:
    def __init__(self):
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def chat(self, user_message: str) -> str:
        # 记录用户消息
        storage.append_conversation("user", user_message)

        self.messages.append({"role": "user", "content": user_message})

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
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
