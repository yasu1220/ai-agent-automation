"""
毎週月曜実行: カンバンの未完了タスクと戦略を元に、今週やることをClaudeが生成して
週次ブリーフに書き込み、カンバンにサブタスク約20件を追加する
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
        "max_tokens": 2048,
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
以下の戦略と現在の未完了タスクを踏まえて、今週の方針と取り組むべきサブタスクを生成してください。

## 戦略
{STRATEGY}

## 現在の未完了タスク（既存）
{task_list}

## カテゴリ一覧
- 法人営業
- 体験セッション
- AIエージェント
- コーチング
- 組織開発
- SNS/YouTube
- 内部整備

## 出力ルール
- 今週の方針を1〜2文（50文字以内）で書く
- 親テーマを3件設定し、それぞれに具体的なサブタスクを6〜7件ずつ生成する（合計約20件）
- サブタスクは毎日3件ずつ消化できる粒度（1〜2時間で完結する具体的なアクション）
- サブタスク名は20文字以内
- カテゴリは上記カテゴリ一覧から選択

## 出力形式
以下のJSON形式のみで出力してください。説明文は不要です：
{{
  "summary": "今週の方針（50文字以内）",
  "themes": [
    {{
      "name": "親テーマ名",
      "category": "カテゴリ名",
      "subtasks": [
        {{"name": "サブタスク名（20文字以内）"}},
        {{"name": "サブタスク名（20文字以内）"}}
      ]
    }}
  ]
}}"""

    response = call_claude(prompt)

    # JSON部分を抽出
    start = response.find("{")
    end = response.rfind("}") + 1
    json_str = response[start:end]
    return json.loads(json_str)


def add_subtasks_to_kanban(themes):
    """サブタスクをカンバンに追加。タスク名はシンプルに、カテゴリプロパティで分類"""
    all_task_ids = []
    for theme in themes:
        category = theme["category"]
        for st in theme["subtasks"]:
            body = {
                "parent": {"database_id": KANBAN_DB_ID},
                "properties": {
                    "タスク名": {
                        "title": [{"text": {"content": st["name"]}}]
                    },
                    "完了": {
                        "checkbox": False
                    },
                    "カテゴリ": {
                        "select": {"name": category}
                    }
                }
            }
            res = notion_request("POST", "/pages", body)
            all_task_ids.append(res["id"])
            print(f"  カンバン追加: {st['name']} [{category}]")
    return all_task_ids


def build_page_content(summary, themes):
    """ページbody用のNotionマークダウンを生成"""
    THEME_ICONS = {
        "法人営業": "🏢",
        "体験セッション": "🧊",
        "AIエージェント": "🤖",
        "コーチング": "💬",
        "組織開発": "🌱",
        "SNS/YouTube": "📱",
        "内部整備": "🔧",
    }
    lines = [
        "## 🎯 今週の方針",
        summary,
        "",
        "---",
        "",
        "## 📋 テーマ別タスク",
    ]
    for theme in themes:
        icon = THEME_ICONS.get(theme["category"], "📌")
        lines.append(f"\n### {icon} {theme['name']}")
        for st in theme["subtasks"]:
            lines.append(f"- {st['name']}")
    return "\n".join(lines)


def create_weekly_plan(week_label, date_str, summary, themes, task_ids):
    relations = [{"id": task_id} for task_id in task_ids]
    page_content = build_page_content(summary, themes)

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
                "rich_text": [{"text": {"content": summary}}]
            },
            "参照タスク": {
                "relation": relations
            }
        },
        "children": _markdown_to_blocks(page_content)
    }
    res = notion_request("POST", "/pages", body)
    return res["url"]


def _markdown_to_blocks(md):
    """シンプルなMarkdown → Notion blocksに変換"""
    blocks = []
    for line in md.split("\n"):
        if line.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                           "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:]}}]}})
        elif line.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:]}}]}})
        elif line.startswith("- "):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
        elif line.strip() == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif line.strip():
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}]}})
    return blocks


def main():
    week_label, date_str = get_week_label()
    print(f"=== 週次ブリーフ生成: {week_label} ===")

    existing_tasks = get_incomplete_tasks()
    print(f"既存の未完了タスク: {len(existing_tasks)}件")

    print("Claude APIで今週のタスクを生成中...")
    result = generate_tasks_and_summary(existing_tasks)

    summary = result["summary"]
    themes = result["themes"]
    total = sum(len(t["subtasks"]) for t in themes)
    print(f"今週の方針: {summary}")
    print(f"生成テーマ: {len(themes)}件 / サブタスク合計: {total}件")

    print("カンバンにサブタスクを追加中...")
    task_ids = add_subtasks_to_kanban(themes)

    print("週間プランを作成中...")
    url = create_weekly_plan(week_label, date_str, summary, themes, task_ids)
    print(f"週次ブリーフ作成: {url}")
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
