"""
毎朝5時実行: 前日のDailyメモ＋直近の週間プランのメモを読んでメモリーページを更新する
"""
import os
import json
import urllib.request
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
def today_jst():
    return datetime.now(JST).date()

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
DAILY_DB_ID = os.environ["NOTION_DAILY_DB_ID"]
WEEKLY_PLAN_DB_ID = os.environ["NOTION_WEEKLY_PLAN_DB_ID"]
MEMORY_PAGE_ID = os.environ["NOTION_MEMORY_PAGE_ID"]
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
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}]
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req) as res:
        result = json.loads(res.read())
        return result["content"][0]["text"]


def get_yesterday_daily_memo():
    """前日のDailyタスクのメモを取得"""
    yesterday = (today_jst() - timedelta(days=1)).strftime("%-m/%-d")
    body = {
        "filter": {
            "property": "日付",
            "title": {"contains": yesterday}
        }
    }
    res = notion_request("POST", f"/databases/{DAILY_DB_ID}/query", body)
    memos = []
    for page in res.get("results", []):
        memo = page["properties"].get("メモ", {}).get("rich_text", [])
        if memo:
            memos.append(memo[0]["plain_text"])
    return "\n".join(memos) if memos else ""


def get_weekly_plan_memo():
    """直近の週間プランのメモを取得（メモが入っているもの最新1件）"""
    body = {
        "sorts": [{"property": "週", "direction": "descending"}],
        "page_size": 5
    }
    res = notion_request("POST", f"/databases/{WEEKLY_PLAN_DB_ID}/query", body)
    for page in res.get("results", []):
        memo = page["properties"].get("メモ", {}).get("rich_text", [])
        if memo and memo[0]["plain_text"].strip():
            week = page["properties"]["週"]["title"]
            week_label = week[0]["plain_text"] if week else "不明"
            return f"【{week_label}】{memo[0]['plain_text']}"
    return ""


def get_current_memory():
    """現在のメモリーページの内容を取得"""
    res = notion_request("GET", f"/blocks/{MEMORY_PAGE_ID}/children")
    lines = []
    for block in res.get("results", []):
        block_type = block["type"]
        if block_type in ("heading_2", "heading_3", "paragraph"):
            rich_text = block[block_type].get("rich_text", [])
            text = "".join(t["plain_text"] for t in rich_text)
            if block_type == "heading_2":
                lines.append(f"## {text}")
            elif block_type == "heading_3":
                lines.append(f"### {text}")
            else:
                lines.append(text)
    return "\n".join(lines)


def update_memory_page(new_content):
    """メモリーページのブロックを全て入れ替える"""
    # 既存ブロックを取得して削除
    res = notion_request("GET", f"/blocks/{MEMORY_PAGE_ID}/children")
    for block in res.get("results", []):
        notion_request("DELETE", f"/blocks/{block['id']}")

    # 新しいブロックを追加
    blocks = []
    for line in new_content.split("\n"):
        if line.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:]}}]}})
        elif line.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                           "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:]}}]}})
        elif line.strip() == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif line.strip():
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}]}})

    # 50件ずつ分割してappend
    for i in range(0, len(blocks), 50):
        notion_request("PATCH", f"/blocks/{MEMORY_PAGE_ID}/children",
                       {"children": blocks[i:i+50]})


def main():
    today = date.today().isoformat()
    print(f"=== メモリー更新: {today} ===")

    daily_memo = get_yesterday_daily_memo()
    weekly_memo = get_weekly_plan_memo()

    if not daily_memo and not weekly_memo:
        print("メモなし。更新をスキップします。")
        return

    current_memory = get_current_memory()

    print(f"前日Dailyメモ: {'あり' if daily_memo else 'なし'}")
    print(f"週間プランメモ: {'あり' if weekly_memo else 'なし'}")

    prompt = f"""あなたは経営者のビジネスアシスタントです。
以下の新しいメモを読んで、現在のメモリーページを更新してください。

## 現在のメモリー
{current_memory}

## 前日のDailyタスクメモ
{daily_memo if daily_memo else "（なし）"}

## 週間プランのメモ
{weekly_memo if weekly_memo else "（なし）"}

## 更新ルール
- 新しいメモの内容を適切なカテゴリに統合・追記する
- 古い情報と矛盾する場合は新しい情報を優先
- 重複する内容はまとめる
- 日付を付記する（{today}）
- 各セクションは ## で始める見出しを維持する

## 出力形式
更新後のメモリーページの全文をそのまま出力してください（見出し含む）。説明文は不要："""

    print("Claude APIでメモリーを更新中...")
    new_memory = call_claude(prompt)
    update_memory_page(new_memory)
    print("=== メモリー更新完了 ===")


if __name__ == "__main__":
    main()
