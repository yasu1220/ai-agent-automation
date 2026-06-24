"""
テスト用: Claude APIが正常に動くか確認するだけ
"""
import os
import json
import urllib.request
import urllib.error

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

def call_claude(prompt):
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 256,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req) as res:
        result = json.loads(res.read())
        return result["content"][0]["text"]

def main():
    response = call_claude("「APIテスト成功」とだけ答えてください。")
    print(f"Claude APIレスポンス: {response}")

if __name__ == "__main__":
    main()
