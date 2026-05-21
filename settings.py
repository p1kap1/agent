"""配置管理模块 —— API Key、Boss Cookie、GitHub Token、模型切换"""

import json
import os
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(PROJECT_DIR, "users.json")
ENV_FILE = os.path.join(PROJECT_DIR, ".env")

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"

MODEL_PRESETS = {
    "deepseek": {
        "name": "DeepSeek",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "key_help": "在 https://platform.deepseek.com/api_keys 获取",
    },
    "openai": {
        "name": "OpenAI",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "key_help": "在 https://platform.openai.com/api-keys 获取",
    },
    "zhipu": {
        "name": "智谱 GLM",
        "model": "glm-4-flash",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "key_help": "在 https://open.bigmodel.cn/usercenter/apikeys 获取",
    },
    "moonshot": {
        "name": "Moonshot",
        "model": "moonshot-v1-8k",
        "base_url": "https://api.moonshot.cn/v1",
        "key_help": "在 https://platform.moonshot.cn 获取",
    },
    "custom": {
        "name": "自定义",
        "model": "",
        "base_url": "",
        "key_help": "填入兼容 OpenAI 接口的 API 地址和 Key",
    },
}


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
    env = _load_env()
    users = _load_users()
    active = users.get("active_user", "default")
    user_cfg = users.get("users", {}).get(active, {})

    model = env.get("OPENAI_MODEL", DEFAULT_MODEL)
    base_url = env.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    provider = "自定义" if env.get("OPENAI_PROVIDER") == "custom" else env.get("OPENAI_PROVIDER", "DeepSeek")

    lines = [
        "## ⚙️ FlowMate 配置",
        "",
        f"**当前用户**: {active}",
        f"**模型厂商**: {provider}",
        f"**模型**: {model}",
        f"**API 地址**: {base_url}",
        f"**API Key**: {mask(env.get('OPENAI_API_KEY', ''))}",
        f"**Boss Cookie**: {mask(user_cfg.get('boss_cookie', ''))}",
    ]

    r = subprocess.run(["git", "remote", "get-url", "origin"],
                       cwd=PROJECT_DIR, capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        lines.append(f"**GitHub**: 已配置")
    else:
        lines.append(f"**GitHub**: 未配置")

    all_users = list(users.get("users", {}).keys())
    if len(all_users) > 1:
        lines.append(f"**其他用户**: {', '.join(u for u in all_users if u != active)}")

    lines.append("")
    lines.append("修改配置：`选择模型` | `设置Key` | `更新Cookie` | `设置GitHub Token` | `切换用户`")

    return "\n".join(lines)


def setup_wizard() -> str:
    """新用户引导设置"""
    env = _load_env()
    users = _load_users()
    active = users.get("active_user", "default")
    user_cfg = users.get("users", {}).get(active, {})

    key_ok = bool(env.get("OPENAI_API_KEY"))
    cookie_ok = bool(user_cfg.get("boss_cookie"))
    git_ok = bool(_check_git_remote())

    lines = [
        "## 👋 FlowMate 配置中心",
        "",
        f"当前用户：**{active}**",
        "",
        "| 配置项 | 状态 | 操作 |",
        "|---|---|---|",
    ]

    provider = env.get("OPENAI_PROVIDER", "deepseek")
    model = env.get("OPENAI_MODEL", DEFAULT_MODEL)
    status = "✅" if key_ok else "❌"
    lines.append(f"| 🧠 模型 | {status} {provider}/{model} | `用DeepSeek` `用OpenAI` `用智谱` |")
    lines.append(f"| 🔑 API Key | {'✅ 已设置' if key_ok else '❌ 未设置'} | `设置Key为sk-xxx` |")
    lines.append(f"| 💼 Boss直聘 | {'✅ 已配置' if cookie_ok else '❌ 未配置'} | `更新Boss Cookie` |")
    lines.append(f"| 📦 GitHub | {'✅ 已配置' if git_ok else '❌ 未配置'} | `设置GitHub Token为ghp_xxx` |")

    lines.append("")
    lines.append("### 支持的 AI 模型")
    for key, preset in MODEL_PRESETS.items():
        if key != "custom":
            lines.append(f"- **{preset['name']}** — `{preset['model']}` → 说「用{key}」")
    lines.append("- **自定义** — 任何兼容 OpenAI 接口的服务 → 说「用自定义模型」")

    all_users = list(users.get("users", {}).keys())
    if len(all_users) > 1:
        lines.append(f"\n其他用户: {', '.join(u for u in all_users if u != active)}")
        lines.append("说「切换用户 名字」切换")

    missing = []
    if not key_ok:
        missing.append("`设置Key为sk-xxx`")
    if not cookie_ok:
        missing.append("`更新Boss Cookie`")
    if not git_ok:
        missing.append("`设置GitHub Token为ghp_xxx`")
    if missing:
        lines.append(f"\n⚠ 待完成：{' · '.join(missing)}")

    return "\n".join(lines)


def _check_git_remote() -> bool:
    r = subprocess.run(["git", "remote", "get-url", "origin"],
                       cwd=PROJECT_DIR, capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())


def select_model(provider: str) -> str:
    """选择 AI 模型厂商和模型"""
    preset = MODEL_PRESETS.get(provider.lower())
    if not preset:
        names = ", ".join(f"`{k}`({v['name']})" for k, v in MODEL_PRESETS.items())
        return f"不支持的模型厂商。可选: {names}"

    env = _load_env()
    env["OPENAI_PROVIDER"] = provider
    if preset["model"]:
        env["OPENAI_MODEL"] = preset["model"]
    if preset["base_url"]:
        env["OPENAI_BASE_URL"] = preset["base_url"]
    _save_env(env)

    msg = f"✅ 已切换到 {preset['name']}（模型: {preset['model']}）"
    if preset["key_help"]:
        msg += f"\n\n🔑 {preset['key_help']}\n请说「设置Key为sk-xxx」配置 API Key。"
    if provider == "custom":
        msg += "\n\n⚠ 自定义模型需额外设置：`设置模型名`、`设置API地址`"
    return msg


def set_api_key(api_key: str) -> str:
    env = _load_env()
    env["OPENAI_API_KEY"] = api_key.strip()
    _save_env(env)
    return f"✅ API Key 已设置为 {mask(api_key)}"


def set_model_name(model: str) -> str:
    env = _load_env()
    env["OPENAI_MODEL"] = model.strip()
    _save_env(env)
    return f"✅ 模型名已改为 `{model}`"


def set_api_base_url(url: str) -> str:
    env = _load_env()
    env["OPENAI_BASE_URL"] = url.strip()
    _save_env(env)
    return f"✅ API 地址已改为 `{url}`"


def set_boss_cookie(cookie: str) -> str:
    users = _load_users()
    active = users.get("active_user", "default")
    users.setdefault("users", {}).setdefault(active, {})["boss_cookie"] = cookie.strip()
    _save_users(users)
    return f"✅ {active} 的 Boss Cookie 已更新"


def set_github_token(token: str) -> str:
    token = token.strip()
    r = subprocess.run(["git", "remote", "get-url", "origin"],
                       cwd=PROJECT_DIR, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return "❌ 未配置 git remote origin，请先运行 git remote add origin <url>"

    old_url = r.stdout.strip()
    if "github.com/" in old_url:
        repo_path = old_url.split("github.com/")[-1].split("@")[-1]
    else:
        repo_path = old_url

    new_url = f"https://{token}@github.com/{repo_path}"
    subprocess.run(["git", "remote", "set-url", "origin", new_url],
                   cwd=PROJECT_DIR, capture_output=True)
    return "✅ GitHub Token 已配置"


def switch_user(username: str) -> str:
    users = _load_users()
    if username not in users.get("users", {}):
        users.setdefault("users", {})[username] = {}
        _save_users(users)
        return f"✅ 已创建用户 `{username}`。请先选择模型并设置 API Key。"
    users["active_user"] = username
    _save_users(users)
    return f"✅ 已切换到 `{username}`"
