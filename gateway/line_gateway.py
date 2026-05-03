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
import os

import requests
from flask import Flask, abort, request

from shared.broker import MQTTBroker

LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")

INBOX_TOPIC = "agents/customer_service/inbox"
OUTBOX_TOPIC = "gateway/outbox"

app = Flask(__name__)
broker = MQTTBroker(client_id="line_gateway")


# ── LINE Push API ─────────────────────────────────────────────────────────────

def push_line(user_id: str, text: str):
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Authorization": f"Bearer {LINE_TOKEN}"},
        json={"to": user_id, "messages": [{"type": "text", "text": text}]},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"[GW] Push API failed {user_id[:8]}: HTTP {resp.status_code} {resp.text}")


# ── MQTT outbox → LINE ────────────────────────────────────────────────────────

def _on_outbox(payload: dict):
    user_id = payload.get("user_id", "")
    content = payload.get("content", "")
    if user_id and content:
        push_line(user_id, content)


# ── Webhook ───────────────────────────────────────────────────────────────────

def _verify_signature(body: bytes, signature: str) -> bool:
    h = hmac.new(LINE_SECRET.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(h).decode() == signature


@app.route("/health")
def health():
    return "ok"


@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    raw_body = request.get_data()

    if LINE_SECRET and not _verify_signature(raw_body, signature):
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
        if not text:
            continue

        broker.publish(INBOX_TOPIC, {
            "user_id": user_id,
            "text": text,
            "timestamp": event.get("timestamp"),
            "source": "line",
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
