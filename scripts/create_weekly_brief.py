"""
毎週月曜5:30実行: 資料置き場（メモリー・戦略・哲学・自己像）＋月次達成度＋カンバンを元に
週間プランとサブタスク約20件を生成してNotionに書き込む
"""
import os
import json
import urllib.request
from datetime import date, timedelta

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
KANBAN_DB_ID = os.environ["NOTION_KANBAN_DB_ID"]
WEEKLY_PLAN_DB_ID = os.environ["NOTION_WEEKLY_PLAN_DB_ID"]
MONTHLY_REPORT_DB_ID = os.environ["NOTION_MONTHLY_REPORT_DB_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# 資料置き場のページID
MEMORY_PAGE_ID = os.environ["NOTION_MEMORY_PAGE_ID"]
STRATEGY_PAGE_ID = os.environ["NOTION_STRATEGY_PAGE_ID"]
PHILOSOPHY_PAGE_ID = os.environ["NOTION_PHILOSOPHY_PAGE_ID"]
SELF_IMAGE_PAGE_ID = os.environ["NOTION_SELF_IMAGE_PAGE_ID"]

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
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}]
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req) as res:
        result = json.loads(res.read())
        return result["content"][0]["text"]


def get_page_text(page_id):
    """Notionページのテキスト内容を取得"""
    res = notion_request("GET", f"/blocks/{page_id}/children")
    lines = []
    for block in res.get("results", []):
        block_type = block["type"]
        if block_type in ("heading_1", "heading_2", "heading_3", "paragraph",
                          "bulleted_list_item", "numbered_list_item"):
            rich_text = block[block_type].get("rich_text", [])
            text = "".join(t["plain_text"] for t in rich_text)
            if block_type == "heading_1":
                lines.append(f"# {text}")
            elif block_type == "heading_2":
                lines.append(f"## {text}")
            elif block_type == "heading_3":
                lines.append(f"### {text}")
            elif block_type in ("bulleted_list_item", "numbered_list_item"):
                lines.append(f"- {text}")
            else:
                lines.append(text)
    return "\n".join(lines)


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


def get_monthly_report():
    """今月の月次達成度を取得"""
    today = date.today()
    month_label = today.strftime("%-m月")
    body = {
        "filter": {
            "property": "月",
            "title": {"contains": month_label}
        }
    }
    res = notion_request("POST", f"/databases/{MONTHLY_REPORT_DB_ID}/query", body)
    results = res.get("results", [])
    if not results:
        return "（月次データなし）"

    page = results[0]
    props = page["properties"]
    lines = [f"## {month_label}の実績"]
    for key, val in props.items():
        if key == "月":
            continue
        if val["type"] == "number" and val.get("number") is not None:
            lines.append(f"- {key}: {val['number']}")
        elif val["type"] == "rich_text":
            text = val["rich_text"]
            if text:
                lines.append(f"- {key}: {text[0]['plain_text']}")
    return "\n".join(lines)


def get_week_label():
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    label = f"{monday.strftime('%Y/%-m/%-d')}-{sunday.strftime('%Y/%-m/%-d')}"
    return label, monday.isoformat()


def generate_tasks_and_summary(memory, strategy, philosophy, self_image,
                                monthly_report, existing_tasks):
    # 最新10件のみ参照（プロンプト長さを抑制）
    recent_tasks = existing_tasks[:10]
    task_list = "\n".join(f"- {t}" for t in recent_tasks) if recent_tasks else "（未完了タスクなし）"

    prompt = f"""あなたは経営者のビジネスアシスタントです。
以下の資料を踏まえて、今週の方針と取り組むべきサブタスクを生成してください。

## 🧠 メモリー（気づき・文脈の蓄積）
{memory}

## 📋 経営戦略2026
{strategy}

## 💭 哲学・価値観
{philosophy}

## 🪞 プロフェッショナルとしての自己像
{self_image}

## 📊 今月の達成度
{monthly_report}

## 現在の未完了タスク（既存・直近10件）
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
- memoは「何をどうやるか」を具体的に2〜3文で書く（ツール名・手順・成果物など）

## 出力形式
以下のJSON形式のみで出力してください。説明文は不要です：
{{
  "summary": "今週の方針（50文字以内）",
  "themes": [
    {{
      "name": "親テーマ名",
      "category": "カテゴリ名",
      "subtasks": [
        {{"name": "サブタスク名（20文字以内）", "memo": "何をどうやるかの具体的な説明（2〜3文）"}},
        {{"name": "サブタスク名（20文字以内）", "memo": "何をどうやるかの具体的な説明（2〜3文）"}}
      ]
    }}
  ]
}}"""

    response = call_claude(prompt)
    start = response.find("{")
    end = response.rfind("}") + 1
    json_str = response[start:end]
    return json.loads(json_str)


def add_subtasks_to_kanban(themes):
    """サブタスクをカンバンに追加。タスク名はシンプルに、memoをページbodyに書き込む"""
    all_task_ids = []
    for theme in themes:
        category = theme["category"]
        for st in theme["subtasks"]:
            memo = st.get("memo", "")
            children = []
            if memo:
                children = [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": memo}}]
                        }
                    }
                ]
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
                },
                "children": children
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
    print(f"=== 週間プラン生成: {week_label} ===")

    print("資料置き場を読み込み中...")
    memory = get_page_text(MEMORY_PAGE_ID)
    strategy = get_page_text(STRATEGY_PAGE_ID)
    philosophy = get_page_text(PHILOSOPHY_PAGE_ID)
    self_image = get_page_text(SELF_IMAGE_PAGE_ID)
    monthly_report = get_monthly_report()

    existing_tasks = get_incomplete_tasks()
    print(f"既存の未完了タスク: {len(existing_tasks)}件")

    print("Claude APIで今週のタスクを生成中...")
    result = generate_tasks_and_summary(
        memory, strategy, philosophy, self_image,
        monthly_report, existing_tasks
    )

    summary = result["summary"]
    themes = result["themes"]
    total = sum(len(t["subtasks"]) for t in themes)
    print(f"今週の方針: {summary}")
    print(f"生成テーマ: {len(themes)}件 / サブタスク合計: {total}件")

    print("カンバンにサブタスクを追加中...")
    task_ids = add_subtasks_to_kanban(themes)

    print("週間プランを作成中...")
    url = create_weekly_plan(week_label, date_str, summary, themes, task_ids)
    print(f"週間プラン作成: {url}")
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
