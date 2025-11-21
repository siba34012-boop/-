#!/usr/bin/env python3
# send_todoist_today.py
"""
Отправляет задачи из Todoist с меткой "@Главное на сегодня" в Telegram.
Проверяет локальное время Europe/Paris и отправляет сообщение только если сейчас 07:00 и день — будний.
Использует переменные окружения:
  TODOIST_TOKEN
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import sys
import requests
from typing import List, Dict

# Переменные окружения (в GitHub Actions лучше задать в Secrets)
TODOIST_TOKEN = os.getenv("TODOIST_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not (TODOIST_TOKEN and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
    print("ERROR: required env vars TODOIST_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID", file=sys.stderr)
    sys.exit(1)

TODOIST_API = "https://api.todoist.com/rest/v2"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
TARGET_LABEL_NAMES = {"@Главное на сегодня", "Главное на сегодня"}

def md_v2_escape(text: str) -> str:
    # Экранирование для MarkdownV2 (Telegram)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join('\\' + c if c in escape_chars else c for c in text)

def get_json(url: str, headers: Dict = None, params: Dict = None):
    resp = requests.get(url, headers=headers or {}, params=params or {}, timeout=20)
    resp.raise_for_status()
    return resp.json()

def fetch_tasks_with_label(label_names: set) -> List[Dict]:
    headers = {"Authorization": f"Bearer {TODOIST_TOKEN}"}
    tasks = get_json(f"{TODOIST_API}/tasks", headers=headers)
    filtered = []
    for t in tasks:
        labels = t.get("labels") or []
        if any(lbl in label_names for lbl in labels):
            filtered.append(t)
    return filtered

def fetch_projects_map() -> Dict[str, str]:
    headers = {"Authorization": f"Bearer {TODOIST_TOKEN}"}
    projects = get_json(f"{TODOIST_API}/projects", headers=headers)
    return {str(p["id"]): p["name"] for p in projects}

def compose_message(tasks: List[Dict], projects_map: Dict[str,str]) -> str:
    now = datetime.now(ZoneInfo("Europe/Paris"))
    header = f"Главное на сегодня\n{now.strftime('%d %b %Y')}\n"
    if not tasks:
        return md_v2_escape(header) + "\n" + md_v2_escape("Список пуст. Нет задач с меткой @Главное на сегодня.")
    def project_name(task):
        return projects_map.get(str(task.get("project_id","")), "")
    tasks_sorted = sorted(tasks, key=lambda t: (project_name(t), t.get("order",0), t.get("content","")))
    parts = [md_v2_escape(header), ""]
    for idx, t in enumerate(tasks_sorted, 1):
        content = md_v2_escape(t.get("content","(без названия)"))
        proj = projects_map.get(str(t.get("project_id","")), "Без проекта")
        proj_escaped = md_v2_escape(proj)
        parts.append(f"{idx}. {content}")
        parts.append(f"_{proj_escaped}_")
        parts.append("")  # пустая строка между задачами
    return "\n".join(parts)

def send_to_telegram(text: str):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    resp = requests.post(TELEGRAM_API, data=payload, timeout=20)
    resp.raise_for_status()
    return resp.json()

def main():
    paris_now = datetime.now(ZoneInfo("Europe/Paris"))
    weekday = paris_now.weekday()  # 0=Mon ... 6=Sun
    hour = paris_now.hour
    # Проверяем будний день и ровно 07 часов
    if weekday >= 5:
        print(f"{paris_now.isoformat()}: Выходной — не отправляем.")
        return
    if hour != 7:
        print(f"{paris_now.isoformat()}: Не 07:00 по Europe/Paris (текущее {hour}:00) — не отправляем.")
        return

    try:
        tasks = fetch_tasks_with_label(TARGET_LABEL_NAMES)
        projects_map = fetch_projects_map()
        msg = compose_message(tasks, projects_map)
        resp = send_to_telegram(msg)
        print("Sent. Telegram response:", resp)
    except Exception as e:
        print("ERROR:", str(e), file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
