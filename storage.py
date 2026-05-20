import json
import os
from datetime import date, datetime

from config import DATA_DIR

CONV_DIR = os.path.join(DATA_DIR, "conversations")
REPORT_DIR = os.path.join(DATA_DIR, "reports")
JOB_FILE = os.path.join(DATA_DIR, "applications.json")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")


def _ensure_dirs():
    os.makedirs(CONV_DIR, exist_ok=True)
    os.makedirs(REPORT_DIR, exist_ok=True)


def _conv_file(date_str: str = None) -> str:
    if date_str is None:
        date_str = date.today().isoformat()
    return os.path.join(CONV_DIR, f"{date_str}.json")


def append_conversation(role: str, content: str, date_str: str = None):
    """追加一条对话记录到当天的日志文件"""
    _ensure_dirs()
    filepath = _conv_file(date_str)
    records = []
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                records = json.load(f)
            except json.JSONDecodeError:
                records = []
    records.append({
        "role": role,
        "content": content,
        "time": datetime.now().isoformat(),
    })
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def load_conversation(date_str: str) -> list[dict]:
    """读取某一天的对话记录"""
    filepath = _conv_file(date_str)
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_report(date_str: str, content: str):
    """保存日报 Markdown 文件"""
    _ensure_dirs()
    filepath = os.path.join(REPORT_DIR, f"{date_str}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


def list_reports() -> list[str]:
    """列出所有已生成的日报文件"""
    _ensure_dirs()
    files = sorted(
        [f for f in os.listdir(REPORT_DIR) if f.endswith(".md")],
        reverse=True,
    )
    return [os.path.join(REPORT_DIR, f) for f in files]


def list_conversation_dates() -> list[str]:
    """列出有对话记录的所有日期"""
    _ensure_dirs()
    dates = sorted(
        [f.replace(".json", "") for f in os.listdir(CONV_DIR) if f.endswith(".json")],
        reverse=True,
    )
    return dates


# ---- 投简历记录 ----

def _load_jobs() -> list[dict]:
    if not os.path.exists(JOB_FILE):
        return []
    with open(JOB_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _save_jobs(jobs: list[dict]):
    with open(JOB_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)


def add_application(company: str, position: str, date_str: str = None,
                    status: str = "已投递", platform: str = "Boss直聘",
                    notes: str = "", **extra) -> dict:
    jobs = _load_jobs()
    new_id = max((j.get("id", 0) for j in jobs), default=0) + 1
    job = {
        "id": new_id,
        "date": date_str or date.today().isoformat(),
        "company": company,
        "position": position,
        "status": status,
        "platform": platform,
        "notes": notes,
        "created_at": datetime.now().isoformat(),
    }
    job.update(extra)
    jobs.append(job)
    _save_jobs(jobs)
    return job


def list_applications(status: str = None, date_str: str = None) -> list[dict]:
    jobs = _load_jobs()
    if status:
        jobs = [j for j in jobs if j["status"] == status]
    if date_str:
        jobs = [j for j in jobs if j["date"] == date_str]
    jobs.sort(key=lambda j: j["date"], reverse=True)
    return jobs


def update_application_status(app_id: int, new_status: str) -> dict | None:
    jobs = _load_jobs()
    for j in jobs:
        if j["id"] == app_id:
            j["status"] = new_status
            _save_jobs(jobs)
            return j
    return None


def delete_application(app_id: int) -> bool:
    jobs = _load_jobs()
    for i, j in enumerate(jobs):
        if j["id"] == app_id:
            jobs.pop(i)
            _save_jobs(jobs)
            return True
    return False


# ---- 上传文件管理 ----

def list_uploads() -> list[str]:
    """列出所有上传的文件"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    files = sorted(
        [f for f in os.listdir(UPLOAD_DIR) if f.endswith(".md") or f.endswith(".txt")],
        reverse=True,
    )
    return [os.path.join(UPLOAD_DIR, f) for f in files]


def read_upload(filename: str) -> str:
    """读取某个上传文件的内容"""
    filepath = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(filepath):
        return ""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def save_upload(filename: str, content: str):
    """保存上传文件"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath
