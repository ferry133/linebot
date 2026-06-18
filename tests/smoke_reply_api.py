"""Smoke test: LINE gateway prefers the Reply API and falls back to Push.

Runs without the runtime deps installed: flask / requests / paho / shared.db
are stubbed so the gateway's real delivery logic can be exercised locally.

Run: python3 tests/smoke_reply_api.py
Exits non-zero on failure so it can be used in CI/pre-commit.
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

failures = []


def check(cond, msg):
    print(("PASS" if cond else "FAIL") + f": {msg}")
    if not cond:
        failures.append(msg)


# ── Stub external deps (not installed locally) ────────────────────────────────

class _FakeResp:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


class _FakeRequests(types.ModuleType):
    def __init__(self):
        super().__init__("requests")
        self.calls = []          # recorded POSTs: list of (url, json)
        self.next_status = 200   # status _the next_ post() returns

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append((url, json))
        return _FakeResp(self.next_status)

    def get(self, url, headers=None, timeout=None):
        return _FakeResp(404, "no profile")  # _upsert_line_user → minimal record


class _FakeMQTTClient:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, _name):
        return lambda *a, **k: None


def _install_stubs():
    fake_requests = _FakeRequests()
    sys.modules["requests"] = fake_requests

    flask = types.ModuleType("flask")

    class _Flask:
        def __init__(self, *a, **k):
            pass

        def route(self, *a, **k):
            return lambda fn: fn

        def run(self, *a, **k):
            pass

    def _abort(code):
        raise RuntimeError(f"abort {code}")

    flask.Flask = _Flask
    flask.abort = _abort
    flask.request = None
    sys.modules["flask"] = flask

    paho = types.ModuleType("paho")
    paho_mqtt = types.ModuleType("paho.mqtt")
    paho_client = types.ModuleType("paho.mqtt.client")
    paho_client.Client = _FakeMQTTClient
    paho_client.CallbackAPIVersion = types.SimpleNamespace(VERSION1=1)
    paho.mqtt = paho_mqtt
    paho_mqtt.client = paho_client
    sys.modules["paho"] = paho
    sys.modules["paho.mqtt"] = paho_mqtt
    sys.modules["paho.mqtt.client"] = paho_client

    shared_db = types.ModuleType("shared.db")
    shared_db.db_exec = lambda *a, **k: None
    sys.modules["shared.db"] = shared_db

    return fake_requests


class _FakeBroker:
    def __init__(self):
        self.published = []  # list of (topic, payload)

    def publish(self, topic, payload):
        self.published.append((topic, payload))


class _FakeRequest:
    """Stand-in for flask.request for the webhook test."""
    def __init__(self, body: bytes, json_obj: dict):
        self._body = body
        self._json = json_obj
        self.headers = {}

    def get_data(self):
        return self._body

    def get_json(self, force=False, silent=False):
        return self._json


def main():
    fake_requests = _install_stubs()

    import gateway.line_gateway as gw

    gw.requests = fake_requests          # ensure module-global points at our stub
    gw.LINE_TOKEN = "test-token"
    gw.LINE_SECRET = ""                  # skip signature verification in webhook
    gw.broker = _FakeBroker()

    REPLY_URL = "https://api.line.me/v2/bot/message/reply"
    PUSH_URL = "https://api.line.me/v2/bot/message/push"

    def reset():
        fake_requests.calls.clear()
        fake_requests.next_status = 200

    def urls():
        return [u for (u, _) in fake_requests.calls]

    # T1 — reply_line success
    reset()
    ok = gw.reply_line("tok-1", "hi")
    check(ok is True, "reply_line returns True on HTTP 200")
    check(urls() == [REPLY_URL], "reply_line hits the Reply endpoint")
    check(fake_requests.calls[0][1].get("replyToken") == "tok-1",
          "reply_line sends the replyToken")

    # T2 — reply_line failure (e.g. expired/used token, 429)
    reset()
    fake_requests.next_status = 429
    ok = gw.reply_line("tok-x", "hi")
    check(ok is False, "reply_line returns False on non-200")

    # T3 — push_line hits the Push endpoint
    reset()
    gw.push_line("U123", "hi")
    check(urls() == [PUSH_URL], "push_line hits the Push endpoint")
    check(fake_requests.calls[0][1].get("to") == "U123", "push_line targets the user id")

    # T4 — _on_outbox: token present + reply 200 ⇒ only Reply, no Push
    reset()
    gw._on_outbox({"user_id": "U1", "content": "hello", "reply_token": "tok"})
    check(urls() == [REPLY_URL], "outbox with valid token uses Reply only (no Push)")

    # T5 — _on_outbox: no token ⇒ Push
    reset()
    gw._on_outbox({"user_id": "U1", "content": "hello"})
    check(urls() == [PUSH_URL], "outbox without token falls back to Push")

    # T6 — _on_outbox: reply fails ⇒ fall back to Push
    reset()
    fake_requests.next_status = 400  # reply rejected (expired/used)
    gw._on_outbox({"user_id": "U1", "content": "hello", "reply_token": "stale"})
    check(urls() == [REPLY_URL, PUSH_URL], "outbox falls back to Push when Reply fails")

    # T7 — _on_outbox: empty content ⇒ nothing sent
    reset()
    gw._on_outbox({"user_id": "U1", "content": ""})
    check(urls() == [], "outbox with empty content sends nothing")

    # T8 — webhook forwards replyToken into the inbox payload
    import json as _json
    event = {"events": [{
        "type": "message",
        "replyToken": "RT-abc",
        "source": {"userId": "U999"},
        "message": {"type": "text", "text": "hi"},
        "timestamp": 1,
    }]}
    gw.request = _FakeRequest(_json.dumps(event).encode(), event)
    gw.broker = _FakeBroker()
    gw.webhook()
    inbox = [p for (t, p) in gw.broker.published if t == gw.INBOX_TOPIC]
    check(len(inbox) == 1, "webhook publishes one inbox message")
    check(inbox and inbox[0].get("reply_token") == "RT-abc",
          "webhook forwards replyToken into the inbox payload")

    # T9 — agent echoes reply_token in BOTH outbox publishes (source-level check;
    #      agent module needs anthropic/etc not installed locally)
    cs_src = open(os.path.join(ROOT, "agents", "customer_service.py"), encoding="utf-8").read()
    check(cs_src.count('"reply_token": reply_token') == 2,
          "customer_service echoes reply_token in both outbox publishes")

    # T10 — proactive notifier untouched: still Push, never Reply
    tn_src = open(os.path.join(ROOT, "trello_line_notifier.py"), encoding="utf-8").read()
    check("message/push" in tn_src and "message/reply" not in tn_src,
          "trello_line_notifier still uses Push only (proactive path unchanged)")

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        sys.exit(1)
    print("All smoke checks passed.")


if __name__ == "__main__":
    main()
