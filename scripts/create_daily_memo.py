"""
毎朝実行: カンバンの未完了タスクを取得して日次メモを自動作成する
"""
import os
import json
import urllib.request
import urllib.error
from datetime import date

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
KANBAN_DB_ID = os.environ["NOTION_KANBAN_DB_ID"]
DAILY_DB_ID = os.environ["NOTION_DAILY_DB_ID"]

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

def notion_request(method, path, body=None):
    url = f"https://api.notion.com/v1{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
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
        tasks.append({"id": page["id"], "name": name})
    return tasks

def create_daily_memo(tasks):
    today = date.today().isoformat()

    # リレーション用タスクID
    relations = [{"id": t["id"]} for t in tasks]

    body = {
        "parent": {"database_id": DAILY_DB_ID},
        "properties": {
            "日付": {
                "title": [{"text": {"content": today}}]
            },
            "Date": {
                "date": {"start": today}
            },
            "タスク": {
                "relation": relations
            }
        }
    }
    res = notion_request("POST", "/pages", body)
    return res["url"]

def main():
    tasks = get_incomplete_tasks()[:3]  # 最大3件
    print(f"未完了タスク（最大3件）: {len(tasks)}件")
    for t in tasks:
        print(f"  - {t['name']}")

    url = create_daily_memo(tasks)
    print(f"日次メモ作成: {url}")

if __name__ == "__main__":
    main()
