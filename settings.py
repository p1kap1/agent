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


def _test_boss_cookie(cookie: str) -> str:
    """探测 Boss直聘 Cookie 是否有效：'valid' | 'expired' | 'error:xxx'"""
    if not cookie:
        return "not_set"
    try:
        import requests
        resp = requests.get(
            "https://www.zhipin.com/wapi/zprelation/interaction/geekGetJob",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0",
                "Cookie": cookie,
                "Referer": "https://www.zhipin.com/web/geek/recommend",
            },
            params={"tag": 5, "page": 1, "pageSize": 1},
            timeout=10,
        )
        if resp.status_code in (401, 302):
            return "expired"
        data = resp.json()
        code = data.get("code")
        if code == 0:
            return "valid"
        if code == 37 or code == 11:  # 未登录/已过期
            return "expired"
        return f"error: code={code}"
    except Exception as e:
        return f"error: {str(e)[:50]}"


def _test_zhaopin_cookie(cookie_json: str) -> str:
    """探测智联 Cookie 是否有效（与实际同步代码用相同端点和参数）"""
    if not cookie_json:
        return "not_set"
    try:
        import json as _json, requests as _requests
        cfg = _json.loads(cookie_json) if isinstance(cookie_json, str) else cookie_json
        cookie_str = cfg.get("cookies", "") if isinstance(cfg, dict) else ""
        ua = cfg.get("userAgent", "Mozilla/5.0") if isinstance(cfg, dict) else "Mozilla/5.0"

        # 提取 at 和 rt（和 zhaopin.py 一致）
        cookies_dict = {}
        for pair in cookie_str.split("; "):
            if "=" in pair:
                k, v = pair.split("=", 1)
                cookies_dict[k] = v
        at = cookies_dict.get("at", "")
        rt = cookies_dict.get("rt", "")

        if not at:
            return "invalid_format"

        # 和 zhaopin.py _request_api 完全一致的调用方式
        resp = _requests.get(
            "https://fe-api.zhaopin.com/c/i/schedule/feedback",
            params={"at": at, "rt": rt, "status": "send", "storeViewCount": "false"},
            headers={
                "User-Agent": ua,
                "Cookie": cookie_str,
                "x-zp-client-id": cookies_dict.get("x-zp-client-id", ""),
                "x-zp-device-sn": cookies_dict.get("x-zp-device-sn", ""),
            },
            timeout=10,
        )
        if resp.status_code in (401, 403):
            return "expired"
        data = resp.json()
        code = data.get("code")
        if code not in (200, 0):
            return "expired"  # 非成功码 = 过期/无效

        # 关键：不仅要 code=200，还要响应体有正常数据结构
        inner = data.get("data")
        if inner is None:
            return "expired"  # data 为 None = Cookie 过期
        if isinstance(inner, dict) and "data" in inner:
            # 正常响应: {"code":200, "data":{"data":[...], "hasNextPage":false}}
            return "valid"
        # data 字段存在但不是 dict 形式（可能被重定向或报错页面）
        return f"error: unexpected response structure"

    except PermissionError:
        return "expired"
    except Exception as e:
        return f"error: {str(e)[:50]}"


def _test_liepin_cookie(cookie: str) -> str:
    """探测猎聘 Cookie 是否有效（与实际同步代码用相同端点和 headers）"""
    if not cookie:
        return "not_set"
    try:
        import requests as _requests, json as _json, uuid as _uuid, time as _time
        xsrf = ""
        for pair in cookie.split("; "):
            if pair.startswith("XSRF-TOKEN="):
                xsrf = pair.split("=", 1)[1]
        if not xsrf:
            return "invalid_format"

        ts = str(int(_time.time() * 1000))

        # 和 liepin.py _request_api 完全一致的 headers
        hdrs = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://c.liepin.com",
            "Referer": "https://c.liepin.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
            "X-Client-Type": "web",
            "X-Fscp-Bi-Stat": '{"location":"https://c.liepin.com/?time=' + ts + '"}',
            "X-Fscp-Std-Info": '{"client_id":"40106"}',
            "X-Fscp-Trace-Id": str(_uuid.uuid4()),
            "X-Fscp-Version": "1.1",
            "X-Requested-With": "XMLHttpRequest",
            "X-XSRF-TOKEN": xsrf,
            "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }

        s = _requests.Session()
        req = _requests.Request(
            "POST",
            "https://api-c.liepin.com/api/com.liepin.capply.pc.apply-list",
            headers=hdrs,
            json={"data": {"status": "applied", "pageSize": 5, "page": 1}},
        )
        prep = s.prepare_request(req)
        prep.headers.update(hdrs)
        prep.headers["Cookie"] = cookie

        resp = s.send(prep, timeout=10)

        if resp.status_code in (401, 403):
            return "expired"

        data = resp.json()
        flag = data.get("flag")

        # flag=1 才是真正的成功；flag=0 可能是无数据但 Cookie 有效
        if flag == 1:
            return "valid"
        if flag == 0:
            # flag=0 可能是：Cookie 有效但无投递记录，也可能是半失效
            # 进一步验证：检查响应体结构完整性
            inner = data.get("data")
            if isinstance(inner, dict) and "data" in inner:
                return "valid"  # 结构完整 = Cookie 有效
            return "expired"  # 结构异常 = Cookie 半失效
        if flag is not None:
            return "expired"  # 其他 flag 值 = 认证错误
        return f"error: no flag in response"

    except PermissionError:
        return "expired"
    except Exception as e:
        return f"error: {str(e)[:50]}"


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
        f"**模型厂商**: {provider}",
        f"**模型**: {model}",
        f"**API 地址**: {base_url}",
        f"**API Key**: {mask(env.get('OPENAI_API_KEY', ''))}",
    ]

    # 三平台 Cookie 状态（带实际探测）
    # Boss
    boss_cookie = user_cfg.get("boss_cookie", "")
    boss_status = _test_boss_cookie(boss_cookie)
    if boss_status == "valid":
        lines.append("**💼 Boss直聘**: ✅ Cookie 有效")
    elif boss_status == "expired":
        lines.append("**💼 Boss直聘**: ⚠️ Cookie 已过期/无效 → 说「更新Boss Cookie」")
    elif boss_status == "not_set":
        lines.append("**💼 Boss直聘**: ❌ 未配置")
    else:
        lines.append(f"**💼 Boss直聘**: ⚠️ 无法验证（{boss_status}）")

    # 智联
    zp = user_cfg.get("zhaopin", {})
    zp_cookie = zp.get("cookie_json", "") if isinstance(zp, dict) else ""
    zp_status = _test_zhaopin_cookie(zp_cookie)
    if zp_status == "valid":
        lines.append("**🔷 智联招聘**: ✅ Cookie 有效")
    elif zp_status == "expired":
        lines.append("**🔷 智联招聘**: ⚠️ Cookie 已过期 → 说「更新智联Cookie」")
    elif zp_status == "not_set":
        lines.append("**🔷 智联招聘**: ❌ 未配置")
    else:
        lines.append(f"**🔷 智联招聘**: ⚠️ 无法验证（{zp_status}）")

    # 猎聘
    lp = user_cfg.get("liepin", {})
    lp_cookie = lp.get("cookie", "") if isinstance(lp, dict) else ""
    lp_status = _test_liepin_cookie(lp_cookie)
    if lp_status == "valid":
        lines.append("**🔶 猎聘**: ✅ Cookie 有效")
    elif lp_status == "expired":
        lines.append("**🔶 猎聘**: ⚠️ Cookie 已过期 → 说「更新猎聘Cookie」")
    elif lp_status == "not_set":
        lines.append("**🔶 猎聘**: ❌ 未配置")
    else:
        lines.append(f"**🔶 猎聘**: ⚠️ 无法验证（{lp_status}）")

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

    # Cookie 有效性检测
    boss_cookie = user_cfg.get("boss_cookie", "")
    boss_status = _test_boss_cookie(boss_cookie)
    zp_cfg = user_cfg.get("zhaopin", {})
    zp_cookie = zp_cfg.get("cookie_json", "") if isinstance(zp_cfg, dict) else ""
    zp_status = _test_zhaopin_cookie(zp_cookie)
    lp_cfg = user_cfg.get("liepin", {})
    lp_cookie = lp_cfg.get("cookie", "") if isinstance(lp_cfg, dict) else ""
    lp_status = _test_liepin_cookie(lp_cookie)
    git_ok = bool(_check_git_remote())

    def _cookie_icon(status: str) -> str:
        if status == "valid":
            return "✅ 有效"
        elif status == "expired":
            return "⚠️ 已过期"
        elif status == "not_set":
            return "❌ 未配置"
        else:
            return f"⚠️ 异常"

    def _cookie_action(status: str, platform: str) -> str:
        if status == "valid":
            return "已就绪"
        cmds = {"Boss": "更新Boss Cookie", "智联": "更新智联Cookie", "猎聘": "更新猎聘Cookie"}
        return f"`{cmds[platform]}`"

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
    lines.append(f"| 💼 Boss直聘 | {_cookie_icon(boss_status)} | {_cookie_action(boss_status, 'Boss')} |")
    lines.append(f"| 🔷 智联招聘 | {_cookie_icon(zp_status)} | {_cookie_action(zp_status, '智联')} |")
    lines.append(f"| 🔶 猎聘 | {_cookie_icon(lp_status)} | {_cookie_action(lp_status, '猎聘')} |")
    lines.append(f"| 📦 GitHub | {'✅ 已配置' if git_ok else '❌ 未配置'} | `设置GitHub Token为ghp_xxx` |")

    lines.append("")
    lines.append("### 支持的 AI 模型")
    for key, preset in MODEL_PRESETS.items():
        if key != "custom":
            lines.append(f"- **{preset['name']}** — `{preset['model']}` → 说「用{key}」")
    lines.append("- **自定义** — 任何兼容 OpenAI 接口的服务 → 说「用自定义模型」")

    # Cookie 配置引导（仅当有未配置/过期时显示）
    cookie_issues = []
    if boss_status in ("not_set", "expired"):
        cookie_issues.append(("💼 Boss直聘", "boss"))
    if zp_status in ("not_set", "expired"):
        cookie_issues.append(("🔷 智联招聘", "zhaopin"))
    if lp_status in ("not_set", "expired"):
        cookie_issues.append(("🔶 猎聘", "liepin"))

    if cookie_issues:
        lines.append("")
        lines.append("### 🔐 如何配置招聘平台 Cookie")
        lines.append("")
        lines.append("**通用步骤：**")
        lines.append("1. 用 Chrome 打开网站并**扫码/短信登录**")
        lines.append("2. 按 `F12` → 选择顶部的 **Application** → 左侧 **Cookies**")
        lines.append("3. 点击网站域名 → 在右侧**全选** `Ctrl+A` → **复制** `Ctrl+C`")
        lines.append("4. 回到这里直接**粘贴发给我**即可，我会自动识别平台并保存")
        lines.append("")
        for name, key in cookie_issues:
            cmd = "更新Boss Cookie" if key == "boss" else f"更新{name}Cookie"
            lines.append(f"- {name}：说「**{cmd}**」然后把 Cookie 粘贴过来")
        lines.append("")
        lines.append("> 💡 也可以直接粘贴 Cookie 内容，说「这是我的XXX Cookie」，AI 会自动识别并更新。")

    all_users = list(users.get("users", {}).keys())
    if len(all_users) > 1:
        lines.append(f"\n其他用户: {', '.join(u for u in all_users if u != active)}")
        lines.append("说「切换用户 名字」切换")

    missing = []
    if not key_ok:
        missing.append("`设置Key为sk-xxx`")
    if boss_status != "valid":
        missing.append("`更新Boss Cookie`")
    if zp_status != "valid":
        missing.append("`更新智联Cookie`")
    if lp_status != "valid":
        missing.append("`更新猎聘Cookie`")
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

    status = _test_boss_cookie(cookie.strip())
    if status == "valid":
        return f"✅ {active} 的 Boss直聘 Cookie 已保存并验证通过！可以正常使用了。"
    elif status == "expired":
        return (
            f"⚠️ Boss直聘 Cookie 已保存，但 **验证失败（已过期）**。\n\n"
            f"请确保：\n"
            f"1. 在浏览器中**当前已登录** Boss直聘\n"
            f"2. 复制的是 **www.zhipin.com** 域名下的 Cookie\n"
            f"3. Cookie 中包含 `zp_at` 和 `wt2` 字段\n\n"
            f"重新获取后说「更新Boss Cookie」再试。"
        )
    else:
        return (
            f"⚠️ Boss直聘 Cookie 已保存，但无法立即验证（{status}）。\n"
            f"可以尝试「同步Boss」来测试。"
        )


def set_zhaopin_cookie(cookie_json: str) -> str:
    """设置智联招聘 Cookie（自动处理浏览器JSON或原始字符串）"""
    users = _load_users()
    active = users.get("active_user", "default")

    raw = cookie_json.strip()
    # 自动检测：如果是JSON格式的cookie列表，转为字符串
    if raw.startswith("[") or (raw.startswith("{") and '"cookies"' in raw):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                pairs = [f"{c.get('name','')}={c.get('value','')}" for c in data if c.get('name')]
                raw = "; ".join(pairs)
            elif isinstance(data, dict) and "cookies" in data:
                raw = data["cookies"]
        except json.JSONDecodeError:
            pass

    # 智联需要保存为JSON对象格式（zhaopin.py读取cookie_json字段）
    cookie_data = json.dumps({"cookies": raw, "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, ensure_ascii=False)
    users.setdefault("users", {}).setdefault(active, {}).setdefault("zhaopin", {})["cookie_json"] = cookie_data
    _save_users(users)

    status = _test_zhaopin_cookie(cookie_data)
    if status == "valid":
        return (
            f"✅ {active} 的智联 Cookie 已保存并验证通过！\n\n"
        )
    elif status == "expired":
        return (
            f"⚠️ 智联 Cookie 已保存，但 **验证失败（已过期）**。\n\n"
            f"请确保：\n"
            f"1. 在浏览器中**当前已登录** 智联招聘\n"
            f"2. 复制的是 **zhaopin.com** 域名下的 Cookie\n"
            f"3. Cookie 中包含 `at` 和 `rt` 字段\n\n"
            f"重新获取后说「更新智联Cookie」再试。"
        )
    else:
        return (
            f"⚠️ 智联 Cookie 已保存，但无法立即验证（{status}）。\n"
            f"可以尝试「同步智联」来测试。"
        )


def set_liepin_cookie(cookie_str: str) -> str:
    """设置猎聘 Cookie 字符串（自动处理浏览器导出的JSON格式）"""
    users = _load_users()
    active = users.get("active_user", "default")

    # 自动检测并转换浏览器 JSON 格式
    raw = cookie_str.strip()
    if raw.startswith("[") or raw.startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                pairs = [f"{c.get('name','')}={c.get('value','')}" for c in data if c.get('name')]
                raw = "; ".join(pairs)
            elif isinstance(data, dict):
                if "cookies" in data:
                    raw = data["cookies"]
                else:
                    pairs = [f"{k}={v}" for k, v in data.items()]
                    raw = "; ".join(pairs)
        except json.JSONDecodeError:
            pass

    users.setdefault("users", {}).setdefault(active, {}).setdefault("liepin", {})["cookie"] = raw
    _save_users(users)

    status = _test_liepin_cookie(raw)
    if status == "valid":
        return f"✅ {active} 的猎聘 Cookie 已保存并验证通过！"
    elif status == "expired":
        return (
            f"⚠️ 猎聘 Cookie 已保存，但 **验证失败（已过期）**。\n\n"
            f"⚠ 猎聘 Cookie 有效期很短（acw_tc IP 绑定），建议操作时临时获取。\n\n"
            f"请确保：\n"
            f"1. 在浏览器中**当前已登录** 猎聘\n"
            f"2. 复制的是 **liepin.com** 域名下的 Cookie\n"
            f"3. Cookie 中包含 `XSRF-TOKEN` 和 `lt_auth` 字段\n\n"
            f"重新获取后说「更新猎聘Cookie」再试。"
        )
    else:
        return (
            f"⚠️ 猎聘 Cookie 已保存，但无法立即验证（{status}）。\n"
            f"可以尝试「同步猎聘」来测试。"
        )


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


def needs_setup() -> bool:
    """检查是否需要引导配置"""
    env = _load_env()
    users = _load_users()
    active = users.get("active_user", "default")
    user_cfg = users.get("users", {}).get(active, {})
    has_key = bool(env.get("OPENAI_API_KEY"))
    dismissed = user_cfg.get("setup_dismissed", False)
    return not has_key and not dismissed


def dismiss_setup() -> str:
    """用户说不需要配置后，取消提醒"""
    users = _load_users()
    active = users.get("active_user", "default")
    users.setdefault("users", {}).setdefault(active, {})["setup_dismissed"] = True
    _save_users(users)
    return "好的，以后不会再提醒。想配置时随时说「查看配置」或「开始设置」。"
