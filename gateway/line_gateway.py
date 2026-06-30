#!/usr/bin/env python3
"""
LINE Gateway — 純 I/O，不含 AI 邏輯

職責：
  IN  → 驗簽 LINE webhook → publish 到 agents/customer_service/inbox
  OUT → 訂閱 gateway/outbox → 呼叫 LINE Push API
"""

import base64
import hashlib
import hmac
import json
import os
import threading

import requests
from flask import Flask, abort, jsonify, request

from shared.broker import MQTTBroker
from shared.db import db_exec

LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
LINE_PROFILE_URL = "https://api.line.me/v2/bot/profile/{}"

INBOX_TOPIC = "agents/customer_service/inbox"
OUTBOX_TOPIC = "gateway/outbox"

app = Flask(__name__)
broker = MQTTBroker(client_id="line_gateway")


# ── LINE user auto-registration ──────────────────────────────────────────────

def _upsert_line_user(user_id: str):
    try:
        resp = requests.get(
            LINE_PROFILE_URL.format(user_id),
            headers={"Authorization": f"Bearer {LINE_TOKEN}"},
            timeout=5,
        )
        if resp.status_code == 200:
            profile = resp.json()
            display_name = profile.get("displayName")
            picture_url = profile.get("pictureUrl")
        else:
            print(f"[GW] Profile API {resp.status_code} for {user_id[:8]}, using minimal record")
            display_name = None
            picture_url = None

        def _do_upsert(conn, _uid=user_id, _dn=display_name, _pu=picture_url):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO line_users (line_id, display_name, picture_url) "
                    "VALUES (%s, %s, %s) "
                    "ON CONFLICT (line_id) DO UPDATE "
                    "SET display_name = EXCLUDED.display_name, "
                    "    picture_url  = EXCLUDED.picture_url, "
                    "    updated_at   = now() "
                    "WHERE line_users.display_name IS DISTINCT FROM EXCLUDED.display_name "
                    "   OR line_users.picture_url  IS DISTINCT FROM EXCLUDED.picture_url",
                    (_uid, _dn, _pu),
                )

        db_exec(_do_upsert)
    except Exception as e:
        print(f"[GW] WARNING: upsert_line_user failed for {user_id[:8]}: {e}")


# ── LINE Push API ─────────────────────────────────────────────────────────────

def _as_messages(payload_or_text) -> list:
    """接受純文字或 LINE message dict 陣列，正規化為 messages 陣列（上限 5 則）。"""
    if isinstance(payload_or_text, str):
        return [{"type": "text", "text": payload_or_text[:5000]}]
    return list(payload_or_text)[:5]


def push_line(user_id: str, messages):
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Authorization": f"Bearer {LINE_TOKEN}"},
        json={"to": user_id, "messages": _as_messages(messages)},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"[GW] Push API failed {user_id[:8]}: HTTP {resp.status_code} {resp.text}")


def reply_line(reply_token: str, messages) -> bool:
    """Reply via the free Reply API. Returns False if the token is unusable."""
    resp = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={"Authorization": f"Bearer {LINE_TOKEN}"},
        json={"replyToken": reply_token, "messages": _as_messages(messages)},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"[GW] Reply API failed: HTTP {resp.status_code} {resp.text}")
        return False
    return True


# ── MQTT outbox → LINE ────────────────────────────────────────────────────────

def _on_outbox(payload: dict):
    user_id = payload.get("user_id", "")
    reply_token = payload.get("reply_token")
    # 支援結構化 messages（Flex 等）或單純 content 文字
    messages = payload.get("messages") or payload.get("content", "")
    if not messages:
        return
    # Prefer the free Reply API; fall back to Push when there is no usable
    # reply token (absent, expired, or already used).
    if reply_token and reply_line(reply_token, messages):
        return
    if user_id:
        push_line(user_id, messages)


# ── Webhook ───────────────────────────────────────────────────────────────────

def _verify_signature(body: bytes, signature: str) -> bool:
    h = hmac.new(LINE_SECRET.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(h).decode() == signature


def _parse_postback(data: str) -> dict:
    """Parse postback `k=v&k=v` data into a dict. Returns {} if empty/malformed."""
    if not data:
        return {}
    out = {}
    for part in data.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out if out.get("o") else {}


@app.route("/health")
def health():
    return "ok"


@app.route("/aliases", methods=["GET"])
def aliases():
    """工期表（Google Apps Script）用：回傳已註冊的 `line_users.alias_name` 清單，
    供其過濾「查無對應」負責人——與 LINE 通知的未對應判定同一套來源。
    以 gateway 既有的 TRELLO_TOKEN 當共用 token（gantt 端 Script Properties 本就有）；
    未設或不符一律回 404（不洩漏端點存在）。單次查詢，呼叫端自行快取。"""
    expected = os.environ.get("TRELLO_TOKEN", "")
    if not expected or request.args.get("token") != expected:
        abort(404)

    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT alias_name FROM line_users "
                "WHERE alias_name IS NOT NULL AND alias_name <> ''"
            )
            return [row[0] for row in cur.fetchall()]

    return jsonify({"aliases": db_exec(_q) or []})


@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    raw_body = request.get_data()

    if LINE_SECRET and not _verify_signature(raw_body, signature):
        abort(400)

    data = request.get_json(force=True, silent=True) or {}
    for event in data.get("events", []):
        etype = event.get("type")
        user_id = event.get("source", {}).get("userId", "unknown")

        if etype == "postback":
            # 工項完成/取消 或 主管確認/退回 — 結構化動作，附原始 data 與解析欄位
            pb = _parse_postback(event.get("postback", {}).get("data", ""))
            if not pb:
                continue
            threading.Thread(target=_upsert_line_user, args=(user_id,), daemon=True).start()
            broker.publish(INBOX_TOPIC, {
                "user_id": user_id,
                "kind": "postback",
                "postback": pb,
                "timestamp": event.get("timestamp"),
                "source": "line",
                "reply_token": event.get("replyToken"),
            })
            continue

        if etype != "message":
            continue
        msg = event.get("message", {})
        if msg.get("type") != "text":
            continue
        text = msg.get("text", "").strip()
        if not text:
            continue

        threading.Thread(target=_upsert_line_user, args=(user_id,), daemon=True).start()

        broker.publish(INBOX_TOPIC, {
            "user_id": user_id,
            "text": text,
            "timestamp": event.get("timestamp"),
            "source": "line",
            "reply_token": event.get("replyToken"),
        })

    return "OK"


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    broker.connect()
    broker.subscribe(OUTBOX_TOPIC, _on_outbox)
    broker.loop_start()  # MQTT 在背景跑

    port = int(os.environ.get("PORT", 8080))
    print(f"[GW] LINE Gateway starting on port {port}...")
    app.run(host="0.0.0.0", port=port)
