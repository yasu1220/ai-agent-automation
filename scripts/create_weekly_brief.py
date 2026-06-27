"""
毎週月曜実行: カンバンの未完了タスクと戦略を元に、今週やることをClaudeが生成して
週次ブリーフに書き込み、カンバンに今週のタスクを追加する
"""
import os
import json
import urllib.request
import urllib.error
from datetime import date, timedelta

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
KANBAN_DB_ID = os.environ["NOTION_KANBAN_DB_ID"]
WEEKLY_PLAN_DB_ID = os.environ["NOTION_WEEKLY_PLAN_DB_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

STRATEGY = """
## ビジョン・ミッション
- Vision: 人間が生きやすい世界を創る
- Mission: 人・組織・社会の変容を起こす

## 2026年フェーズ計画
- フェーズ1（5〜7月）仕込み期: 自己の内面・外面を磨き、8月のバズに対応する準備構築
- 6月目標: 月商40万円（法人1件×30万、個人5人×2万）、法人登記
- 7月目標: 月商40万円、EX旅

## 事業領域
- コーチング / 組織開発
- 極限体験（アイスバス・呼吸法）
- 瞑想サービス
- パブリッシング（YouTube / SNS）
"""


def notion_request(method, path, body=None):
    url = f"https://api.notion.com/v1{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=NOTION_HEADERS, method=method)
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read())


def get_incomplete_tasks():
    body = {
        "filter": {
            "property": "完了",
            "checkbox": {"equals": False}
        }
    }
    res = notion_request("POST", f"/databases/{KANBAN_DB_ID}/query", body)
    tasks = []
    for page in res.get("results", []):
        title = page["properties"]["タスク名"]["title"]
        name = title[0]["plain_text"] if title else "（無題）"
        tasks.append(name)
    return tasks


def call_claude(prompt):
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}]
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req) as res:
        result = json.loads(res.read())
        return result["content"][0]["text"]


def get_week_label():
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    label = f"{monday.strftime('%Y/%-m/%-d')}-{sunday.strftime('%Y/%-m/%-d')}"
    return label, monday.isoformat()


def generate_tasks_and_summary(existing_tasks):
    task_list = "\n".join(f"- {t}" for t in existing_tasks) if existing_tasks else "（未完了タスクなし）"

    prompt = f"""あなたは経営者のビジネスアシスタントです。
以下の戦略と現在の未完了タスクを踏まえて、今週新たに取り組むべきタスクを3件提案してください。

## 戦略
{STRATEGY}

## 現在の未完了タスク（既存）
{task_list}

## 出力形式
以下のJSON形式のみで出力してください。説明文は不要です：
{{
  "summary": "今週の方針を1〜2文で（50文字以内）",
  "tasks": [
    {{"name": "タスク名（20文字以内）", "priority": "高"}},
    {{"name": "タスク名（20文字以内）", "priority": "中"}},
    {{"name": "タスク名（20文字以内）", "priority": "低"}}
  ]
}}"""

    response = call_claude(prompt)

    # JSON部分を抽出
    start = response.find("{")
    end = response.rfind("}") + 1
    json_str = response[start:end]
    return json.loads(json_str)


def add_tasks_to_kanban(tasks, week_label):
    added_ids = []
    for t in tasks:
        body = {
            "parent": {"database_id": KANBAN_DB_ID},
            "properties": {
                "タスク名": {
                    "title": [{"text": {"content": f"[{week_label}] {t['name']}"}}]
                },
                "完了": {
                    "checkbox": False
                }
            }
        }
        res = notion_request("POST", "/pages", body)
        added_ids.append(res["id"])
        print(f"  カンバン追加: {t['name']} (優先度:{t['priority']})")
    return added_ids


def create_weekly_plan(week_label, date_str, summary, tasks, task_ids):
    task_lines = "\n".join(
        f"{i+1}. 【{t['priority']}】{t['name']}" for i, t in enumerate(tasks)
    )
    content = f"{summary}\n\n【今週のタスク】\n{task_lines}"

    relations = [{"id": task_id} for task_id in task_ids]

    body = {
        "parent": {"database_id": WEEKLY_PLAN_DB_ID},
        "properties": {
            "週": {
                "title": [{"text": {"content": week_label}}]
            },
            "Date": {
                "date": {"start": date_str}
            },
            "今週やること": {
                "rich_text": [{"text": {"content": content}}]
            },
            "参照タスク": {
                "relation": relations
            }
        }
    }
    res = notion_request("POST", "/pages", body)
    return res["url"]


def main():
    week_label, date_str = get_week_label()
    print(f"=== 週次ブリーフ生成: {week_label} ===")

    existing_tasks = get_incomplete_tasks()
    print(f"既存の未完了タスク: {len(existing_tasks)}件")

    print("Claude APIで今週のタスクを生成中...")
    result = generate_tasks_and_summary(existing_tasks)

    summary = result["summary"]
    new_tasks = result["tasks"]
    print(f"今週の方針: {summary}")

    print("カンバンにタスクを追加中...")
    task_ids = add_tasks_to_kanban(new_tasks, week_label)

    print("週間プランを作成中...")
    url = create_weekly_plan(week_label, date_str, summary, new_tasks, task_ids)
    print(f"週次ブリーフ作成: {url}")
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
