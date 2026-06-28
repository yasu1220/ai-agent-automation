"""
毎朝6時実行: カンバンの未完了タスクから3件選んでDailyタスクに追加する
"""
import os
import json
import urllib.request
from datetime import date

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
KANBAN_DB_ID = os.environ["NOTION_KANBAN_DB_ID"]
DAILY_DB_ID = os.environ["NOTION_DAILY_DB_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


def notion_request(method, path, body=None):
    url = f"https://api.notion.com/v1{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=NOTION_HEADERS, method=method)
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read())


def call_claude(prompt):
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 512,
        "messages": [{"role": "user", "content": prompt}]
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req) as res:
        result = json.loads(res.read())
        return result["content"][0]["text"]


def get_incomplete_tasks():
    """カンバンの未完了タスクをID付きで取得"""
    body = {
        "filter": {
            "property": "完了",
            "checkbox": {"equals": False}
        },
        "page_size": 100
    }
    res = notion_request("POST", f"/databases/{KANBAN_DB_ID}/query", body)
    tasks = []
    for page in res.get("results", []):
        title = page["properties"]["タスク名"]["title"]
        name = title[0]["plain_text"] if title else "（無題）"
        category = page["properties"].get("カテゴリ", {}).get("select")
        category_name = category["name"] if category else "未分類"
        tasks.append({
            "id": page["id"],
            "name": name,
            "category": category_name
        })
    return tasks


def select_tasks_with_claude(tasks):
    """Claudeに今日やるべき3件を選ばせる"""
    task_list = "\n".join(
        f"{i+1}. [{t['category']}] {t['name']}"
        for i, t in enumerate(tasks)
    )

    prompt = f"""あなたは経営者のビジネスアシスタントです。
以下のカンバンの未完了タスク一覧から、今日取り組むべき3件を選んでください。

## 選定基準
- カテゴリのバランスを取る（同じカテゴリに偏らない）
- 具体的で今日中に完結できそうなもの
- 事業インパクトが高いものを優先

## タスク一覧
{task_list}

## 出力形式
以下のJSON形式のみで出力してください。説明文は不要です：
[
  {{"index": タスクの番号（1始まり）}},
  {{"index": タスクの番号（1始まり）}},
  {{"index": タスクの番号（1始まり）}}
]"""

    response = call_claude(prompt)
    start = response.find("[")
    end = response.rfind("]") + 1
    selected = json.loads(response[start:end])
    return [tasks[s["index"] - 1] for s in selected]


def get_or_create_today_daily():
    """今日のDailyタスクページを取得または作成"""
    today = date.today()
    label = today.strftime("%-m/%-d")

    # 既存ページを検索
    body = {
        "filter": {
            "property": "日付",
            "title": {"equals": label}
        }
    }
    res = notion_request("POST", f"/databases/{DAILY_DB_ID}/query", body)
    results = res.get("results", [])

    if results:
        return results[0]["id"]

    # 新規作成
    body = {
        "parent": {"database_id": DAILY_DB_ID},
        "properties": {
            "日付": {
                "title": [{"text": {"content": label}}]
            }
        }
    }
    res = notion_request("POST", "/pages", body)
    return res["id"]


def add_tasks_to_daily(daily_page_id, selected_tasks):
    """選んだタスクをDailyタスクのリレーションに追加"""
    relations = [{"id": t["id"]} for t in selected_tasks]
    body = {
        "properties": {
            "タスク": {
                "relation": relations
            }
        }
    }
    notion_request("PATCH", f"/pages/{daily_page_id}", body)


def main():
    today = date.today().isoformat()
    print(f"=== Dailyタスク選定: {today} ===")

    tasks = get_incomplete_tasks()
    print(f"未完了タスク: {len(tasks)}件")

    if not tasks:
        print("タスクなし。終了します。")
        return

    if len(tasks) < 3:
        selected = tasks
    else:
        print("Claudeが今日の3件を選定中...")
        selected = select_tasks_with_claude(tasks)

    print("選定されたタスク:")
    for t in selected:
        print(f"  [{t['category']}] {t['name']}")

    daily_page_id = get_or_create_today_daily()
    add_tasks_to_daily(daily_page_id, selected)
    print(f"Dailyタスクに追加完了")
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
