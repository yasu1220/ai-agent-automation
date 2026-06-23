"""
テスト用: Notionに「テスト」ページを1つ作るだけ
実行前に環境変数を設定してください:
  $env:NOTION_TOKEN = "secret_xxxx"
  $env:NOTION_DAILY_DB_ID = "2496f581-4e19-408b-aa41-97ecfe124139"
"""
import os
import json
import urllib.request
from datetime import date

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
DAILY_DB_ID = os.environ["NOTION_DAILY_DB_ID"]

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

body = {
    "parent": {"database_id": DAILY_DB_ID},
    "properties": {
        "日付": {
            "title": [{"text": {"content": "テスト"}}]
        }
    }
}

req = urllib.request.Request(
    "https://api.notion.com/v1/pages",
    data=json.dumps(body).encode(),
    headers=HEADERS,
    method="POST"
)

try:
    with urllib.request.urlopen(req) as res:
        result = json.loads(res.read())
        print(f"成功！ページURL: {result['url']}")
except urllib.error.HTTPError as e:
    print(f"失敗: {e.code} {e.reason}")
    print(e.read().decode())
