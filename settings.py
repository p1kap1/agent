"""配置管理模块 —— 统一管理 API Key、Boss Cookie、GitHub Token 等敏感配置"""

import json
import os
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(PROJECT_DIR, "users.json")
ENV_FILE = os.path.join(PROJECT_DIR, ".env")


def _load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {"active_user": "default", "users": {}}
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_users(data: dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_env() -> dict:
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def _save_env(env: dict):
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")


def mask(value: str) -> str:
    if not value:
        return "(未设置)"
    if len(value) <= 12:
        return value[:4] + "****"
    return value[:6] + "****" + value[-4:]


def show_settings() -> str:
    """查看当前配置（敏感信息脱敏）"""
    env = _load_env()
    users = _load_users()
    active = users.get("active_user", "default")
    user_cfg = users.get("users", {}).get(active, {})

    lines = [
        "## ⚙️ FlowMate 配置",
        "",
        f"**当前用户**: {active}",
        f"**DeepSeek Key**: {mask(env.get('OPENAI_API_KEY', ''))}",
        f"**DeepSeek Model**: {env.get('OPENAI_MODEL', '')}",
        f"**Boss Cookie**: {mask(user_cfg.get('boss_cookie', ''))}",
    ]

    # Git remote
    r = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=PROJECT_DIR, capture_output=True, text=True,
    )
    if r.returncode == 0:
        remote = r.stdout.strip()
        if "@" in remote:
            remote = remote.split("@")[0][:10] + "****@" + remote.split("@")[1] if "@" in remote else "****"
        lines.append(f"**GitHub Remote**: {mask(remote)}")

    # List other users
    all_users = list(users.get("users", {}).keys())
    if len(all_users) > 1:
        lines.append(f"**其他用户**: {', '.join(u for u in all_users if u != active)}")

    lines.append("")
    lines.append("修改配置：`设置DeepSeek Key为sk-xxx` | `设置Boss Cookie` | `设置GitHub Token` | `切换用户`")

    return "\n".join(lines)


def set_deepseek_key(api_key: str) -> str:
    """设置 DeepSeek API Key"""
    env = _load_env()
    env["OPENAI_API_KEY"] = api_key.strip()
    _save_env(env)
    return f"✅ DeepSeek API Key 已更新为 {mask(api_key)}"


def set_boss_cookie(cookie: str) -> str:
    """设置当前用户的 Boss直聘 Cookie"""
    users = _load_users()
    active = users.get("active_user", "default")
    users.setdefault("users", {}).setdefault(active, {})["boss_cookie"] = cookie.strip()
    _save_users(users)
    return f"✅ {active} 的 Boss Cookie 已更新"


def set_github_token(token: str) -> str:
    """设置 GitHub Token 并更新 git remote"""
    token = token.strip()
    r = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=PROJECT_DIR, capture_output=True, text=True,
    )
    if r.returncode != 0:
        return "❌ 未配置 git remote origin"

    old_url = r.stdout.strip()
    # Extract repo path from old URL
    if "github.com/" in old_url:
        repo_path = old_url.split("github.com/")[-1].split("@")[-1]
    else:
        repo_path = old_url

    new_url = f"https://{token}@github.com/{repo_path}"
    subprocess.run(["git", "remote", "set-url", "origin", new_url],
                   cwd=PROJECT_DIR, capture_output=True)

    return f"✅ GitHub Token 已更新并配置到 git remote"


def switch_user(username: str) -> str:
    """切换到指定用户配置"""
    users = _load_users()
    if username not in users.get("users", {}):
        users.setdefault("users", {})[username] = {}
        _save_users(users)
        return f"✅ 已创建新用户 `{username}` 并切换。请设置该用户的 Boss Cookie。"
    users["active_user"] = username
    _save_users(users)
    return f"✅ 已切换到用户 `{username}`"


def add_user(username: str) -> str:
    """添加新用户"""
    users = _load_users()
    if username in users.get("users", {}):
        return f"用户 `{username}` 已存在。说「切换用户 {username}」即可。"
    users.setdefault("users", {})[username] = {}
    _save_users(users)
    return f"✅ 已添加用户 `{username}`，说「切换用户 {username}」即可使用。"
