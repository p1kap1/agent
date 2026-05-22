"""FlowMate 外部工具 — 网页搜索 + 浏览器自动化"""

import json
import os
import time


def web_search(query: str, max_results: int = 5) -> str:
    """搜索引擎查询，返回 Markdown 格式结果"""
    try:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(r)
        if not results:
            return f'未找到与 "{query}" 相关的结果。'

        lines = [f'## 🔍 搜索: {query}', ""]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **[{r.get('title', '')}]({r.get('href', '')})**")
            lines.append(f"   {r.get('body', '')[:200]}")
            lines.append("")
        return "\n".join(lines)

    except ImportError:
        return "搜索模块未安装（pip install ddgs）。"
    except Exception as e:
        return f"搜索失败: {e}"


def search_for_knowledge(topic: str) -> str:
    """为日报推荐知识时搜索最新资料"""
    try:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(f"{topic} tutorial best practices", max_results=3):
                results.append(f"- [{r.get('title','')}]({r.get('href','')})")
        if results:
            return f"关于 **{topic}** 的最新资料：\n" + "\n".join(results[:5])
    except Exception:
        pass
    return ""


def refresh_liepin_cookie() -> str:
    """尝试通过本地 Chrome 刷新猎聘 Cookie"""
    import subprocess
    import tempfile

    # 查找 Chrome
    chrome_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/opt/google/chrome/chrome",
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    ]
    chrome = None
    for p in chrome_paths:
        if os.path.exists(p):
            chrome = p
            break

    if not chrome:
        return (
            "未找到 Chrome 浏览器。请手动刷新 Cookie：\n"
            "1. 打开猎聘网页\n"
            "2. F12 → Application → Cookies\n"
            "3. 复制所有 cookie → 发给我"
        )

    # 输出临时脚本供用户手动运行
    script = f"""#!/bin/bash
# 关闭已有 Chrome 进程
pkill chrome 2>/dev/null
sleep 1

# 启动 Chrome 远程调试模式（请手动登录猎聘）
"{chrome}" \\
  --remote-debugging-port=9222 \\
  --user-data-dir=/tmp/flowmate_chrome \\
  https://c.liepin.com/ &

echo "Chrome 已启动，请在浏览器中登录猎聘"
echo "登录完成后按 Enter 继续..."
read

# 提取 Cookie
curl -s http://localhost:9222/json | python3 -c "
import json, sys
pages = json.load(sys.stdin)
for p in pages:
    if 'liepin' in p.get('url', ''):
        print('FOUND:', p['url'])
        print('DEBUG_PORT:', p.get('webSocketDebuggerUrl', ''))
"
"""
    script_path = os.path.join(tempfile.gettempdir(), "flowmate_refresh_liepin.sh")
    with open(script_path, "w") as f:
        f.write(script)
    os.chmod(script_path, 0o755)

    return (
        f"请在终端运行以下命令来刷新猎聘 Cookie：\n\n"
        f"```bash\nbash {script_path}\n```\n\n"
        f"Chrome 会自动打开猎聘页面，登录后脚本会提取 Cookie。"
    )
