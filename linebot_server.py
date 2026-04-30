#!/usr/bin/env python3
"""
LINE Bot Webhook Server — 意念情境室內裝修 客服 Robot

接收 LINE 訊息 → Claude API 理解問題 → 查詢 Trello / 公司資訊 → 回覆客戶
無法回答時 → 推播到管理群組 + 告知客戶已轉交

執行：python linebot_server.py
"""

import os
import json
import hmac
import hashlib
import base64
from datetime import datetime

import anthropic
import requests
from flask import Flask, request, abort

from trello_line_notifier import (
    TAIPEI,
    get_boards,
    get_lists,
    get_cards,
    parse_tag,
    days_diff,
    send_line,
)

# ── 環境變數 ──────────────────────────────────────────────────────────────────
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
LINE_NOTIFY_GROUP_ID = os.environ.get("LINE_NOTIFY_GROUP_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"
MODEL = "claude-haiku-4-5-20251001"
MAX_HISTORY = 20   # 每位用戶保留最近 N 則對話
MAX_TOOL_TURNS = 5  # agentic loop 最多輪次

# ── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """你是「意念情境室內裝修」的 LINE 客服助理。

【公司簡介】
意念情境室內裝修提供住宅與商業空間的設計、施工與監工服務，服務範圍包含全室裝修、局部改造、木作工程、水電配管、地板磁磚等。

【你能回答的問題】
- 公司服務項目、施工流程、報價方式
- 工程進度、各工班預計到場時間、工項排程
- 費用說明、付款階段、付款狀態（從工程看板查詢）
- 材料選樣、工期估算等一般諮詢

【回應原則】
- 語氣親切、專業，使用繁體中文
- 回答要具體有幫助，若資訊不足可主動說明需要哪些資訊
- 查詢工程進度時，先用 query_trello 工具取得即時資料再回答
- 遇到無法確定、需要人工判斷、或涉及合約細節的問題，使用 escalate_to_manager 工具轉交專人

【不要做的事】
- 不要編造工程進度或日期
- 不要承諾具體報價金額（引導客戶預約現場勘查）
- 不要提供個人資料或其他客戶資訊
"""

# ── 工具定義 ──────────────────────────────────────────────────────────────────
TOOLS = [
    {
        "name": "query_trello",
        "description": "查詢 Trello 工程看板的即時資料，包含所有工項進度、排程、逾期狀況等。查詢客戶工程進度時請使用此工具。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": ["all", "overdue", "upcoming", "specific"],
                    "description": "all=全部工項概況, overdue=逾期工項, upcoming=7天內到期, specific=關鍵字搜尋"
                },
                "keyword": {
                    "type": "string",
                    "description": "query_type=specific 時的搜尋關鍵字（客戶姓名、工項名稱、看板名稱）"
                }
            },
            "required": ["query_type"]
        }
    },
    {
        "name": "escalate_to_manager",
        "description": "當問題超出客服範圍、需要人工判斷、或無法確定答案時，通知管理人員處理。呼叫後系統會自動推播給管理群組，並告知客戶已轉交專人。",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "無法回答的原因或需要專人處理的說明"
                },
                "customer_question": {
                    "type": "string",
                    "description": "客戶原始問題（方便管理人員了解情況）"
                }
            },
            "required": ["reason", "customer_question"]
        }
    }
]

# ── 對話記憶 ──────────────────────────────────────────────────────────────────
_history: dict[str, list] = {}  # user_id → messages[]


def get_history(user_id: str) -> list:
    return list(_history.get(user_id, []))


def append_history(user_id: str, messages: list):
    h = _history.get(user_id, [])
    h.extend(messages)
    _history[user_id] = h[-MAX_HISTORY:]


# ── Trello 查詢工具 ───────────────────────────────────────────────────────────
def _scan_all_items() -> list[dict]:
    """掃描所有看板，回傳工項清單"""
    boards = get_boards()
    items = []
    for board in boards:
        if "母版" in board["name"]:
            continue
        list_map = get_lists(board["id"])
        cards = get_cards(board["id"])
        for card in cards:
            list_name = list_map.get(card.get("idList", ""), "")

            # Card description 第一行
            if card.get("desc"):
                parsed = parse_tag(card["desc"].split("\n")[0])
                if parsed:
                    names, start, end, end_time, label = parsed
                    items.append({
                        "board": board["name"], "list": list_name,
                        "card": card["name"], "label": label or card["name"],
                        "names": names, "start": str(start), "end": str(end),
                        "source": "card_desc",
                    })

            # Checklist 項目
            for cl in card.get("checklists", []):
                for item in cl.get("checkItems", []):
                    parsed = parse_tag(item["name"])
                    if not parsed:
                        continue
                    names, start, end, end_time, label = parsed
                    items.append({
                        "board": board["name"], "list": list_name,
                        "card": card["name"], "label": label,
                        "names": names, "start": str(start), "end": str(end),
                        "state": item["state"], "source": "checklist",
                    })
    return items


def execute_query_trello(query_type: str, keyword: str = "") -> str:
    try:
        items = _scan_all_items()
    except Exception as e:
        return f"查詢 Trello 失敗：{e}"

    if not items:
        return "目前 Trello 無任何有標記的工項。"

    if query_type == "overdue":
        filtered = [i for i in items if i["end"] != "None" and days_diff(
            __import__("datetime").date.fromisoformat(i["end"])) < 0]
        label = "逾期工項"
    elif query_type == "upcoming":
        filtered = [i for i in items if i["end"] != "None" and 0 <= days_diff(
            __import__("datetime").date.fromisoformat(i["end"])) <= 7]
        label = "7 天內到期工項"
    elif query_type == "specific" and keyword:
        kw = keyword.lower()
        filtered = [i for i in items if kw in i["board"].lower()
                    or kw in i["card"].lower() or kw in i["label"].lower()
                    or any(kw in n for n in i["names"])]
        label = f"關鍵字「{keyword}」相關工項"
    else:
        filtered = items
        label = "所有工項"

    if not filtered:
        return f"查無{label}。"

    now = datetime.now(TAIPEI).strftime("%Y/%m/%d %H:%M")
    lines = [f"📋 {label}（查詢時間：{now}，共 {len(filtered)} 項）\n"]
    for i in filtered:
        state_str = ""
        if i.get("state") == "complete":
            state_str = " ✓"
        elif i.get("state") == "incomplete":
            state_str = " ⬜"
        end_str = f"，到期：{i['end']}" if i["end"] != "None" else ""
        lines.append(
            f"・{i['board']} / {i['list']} / {i['card']}\n"
            f"  {i['label']}{state_str}{end_str}"
        )
    return "\n".join(lines)


# ── 升級通知 ──────────────────────────────────────────────────────────────────
def execute_escalate(reason: str, customer_question: str, source_user_id: str) -> str:
    now = datetime.now(TAIPEI).strftime("%Y/%m/%d %H:%M")
    msg = (
        f"⚠️ LINE 客服轉交通知\n"
        f"時間：{now}\n"
        f"客戶問題：{customer_question}\n"
        f"原因：{reason}\n"
        f"客戶 ID：{source_user_id[:8]}..."
    )
    if LINE_NOTIFY_GROUP_ID:
        send_line(LINE_NOTIFY_GROUP_ID, msg)
    else:
        # fallback：嘗試從 contacts 推播給 SA / Larry
        try:
            from trello_line_notifier import load_contacts
            contacts = load_contacts()
            for name in ("sa", "larry"):
                uid = contacts.get(name)
                if uid:
                    send_line(uid, msg)
        except Exception:
            pass
    return "escalated"


# ── Claude Agentic Loop ───────────────────────────────────────────────────────
def ask_claude(user_id: str, user_message: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    history = get_history(user_id)
    new_messages = [{"role": "user", "content": user_message}]

    escalated = False
    final_text = ""

    for _ in range(MAX_TOOL_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=history + new_messages,
            tools=TOOLS,
        )

        new_messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    final_text = block.text
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if block.name == "query_trello":
                    result = execute_query_trello(
                        block.input.get("query_type", "all"),
                        block.input.get("keyword", ""),
                    )
                elif block.name == "escalate_to_manager":
                    execute_escalate(
                        block.input.get("reason", ""),
                        block.input.get("customer_question", user_message),
                        user_id,
                    )
                    escalated = True
                    result = "已通知管理人員。"
                else:
                    result = "未知工具。"
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
            new_messages.append({"role": "user", "content": tool_results})
        else:
            break

    append_history(user_id, new_messages)

    if escalated and not final_text:
        final_text = "您好，您的問題已轉交給專人處理，我們會盡快與您聯繫，感謝您的耐心等候！"

    return final_text[:5000] if final_text else "抱歉，目前無法處理您的問題，已通知專人跟進。"


# ── LINE API ──────────────────────────────────────────────────────────────────
def verify_signature(body: bytes, signature: str) -> bool:
    h = hmac.new(LINE_SECRET.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(h).decode() == signature


def reply_line(reply_token: str, message: str):
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": message}],
    }
    requests.post(LINE_REPLY_API, headers=headers, json=body)


# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)


@app.route("/health")
def health():
    return "ok"


@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    raw_body = request.get_data()

    if LINE_SECRET and not verify_signature(raw_body, signature):
        abort(400)

    data = request.get_json(force=True, silent=True) or {}
    for event in data.get("events", []):
        if event.get("type") != "message":
            continue
        msg = event.get("message", {})
        if msg.get("type") != "text":
            continue

        user_id = event.get("source", {}).get("userId", "unknown")
        text = msg.get("text", "").strip()
        reply_token = event.get("replyToken", "")

        if not text:
            continue

        response_text = ask_claude(user_id, text)
        reply_line(reply_token, response_text)

    return "OK"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting LINE Bot server on port {port}...")
    app.run(host="0.0.0.0", port=port)
