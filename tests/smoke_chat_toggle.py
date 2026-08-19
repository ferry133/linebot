"""smoke: 驗證 CHAT_ENABLED 開關：關閉時只擋自由對話 fallback，其餘入口不變。

刻意不 stub customer_service 本身的 import 鏈（真的載入模組），只把
外部副作用（DB / anthropic client / MQTT broker / handler）換掉，
避免驗到的是自己編的 fixture 而不是真程式碼。

跑法：python3 tests/smoke_chat_toggle.py（需已安裝 anthropic / paho-mqtt / psycopg2-binary 等依賴）
"""
import os, sys, importlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy")
os.environ.setdefault("TRELLO_API_KEY", "dummy")
os.environ.setdefault("TRELLO_TOKEN", "dummy")
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/none")

FAILS = []
def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

def load(chat_enabled_value):
    """以指定的 CHAT_ENABLED 值重新載入模組（module-level 常數，需 reload）。"""
    for m in [m for m in list(sys.modules) if m.startswith("agents.customer_service")]:
        del sys.modules[m]
    if chat_enabled_value is None:
        os.environ.pop("CHAT_ENABLED", None)
    else:
        os.environ["CHAT_ENABLED"] = chat_enabled_value
    return importlib.import_module("agents.customer_service")


class FakeBroker:
    def __init__(self): self.published = []
    def subscribe(self, *a, **k): pass
    def publish(self, topic, payload): self.published.append((topic, payload))


def make_agent(cs):
    """真的 CustomerServiceAgent，但不建立 anthropic client / DB pool。"""
    agent = cs.CustomerServiceAgent.__new__(cs.CustomerServiceAgent)
    agent.broker = FakeBroker()
    agent._pending = {}
    calls = {"claude": 0, "memory": 0}

    class BoomClient:      # 任何 Claude 呼叫都要炸，才能證明「沒呼叫」
        class messages:
            @staticmethod
            def create(*a, **k):
                calls["claude"] += 1
                raise AssertionError("Anthropic API called while chat disabled")
    class BoomMemory:
        def __getattr__(self, name):
            def _f(*a, **k):
                calls["memory"] += 1
                raise AssertionError(f"memory.{name} called while chat disabled")
            return _f
    agent.client = BoomClient()
    agent.memory = BoomMemory()
    return agent, calls


def route(agent, cs, payload, handlers_seen, forwarded=None, done=None):
    """換掉各 handler 記錄被叫到誰；_process 也換掉（避免真的跑 Claude thread）。"""
    if forwarded is not None:
        def _fwd(user_id, text, group_id=None):
            forwarded.append((user_id, text, group_id))
            if done is not None:
                done.set()
        agent._forward_offline_message = _fwd
    for name in ("_handle_guide", "_handle_daily", "_handle_future", "_process",
                 "_process_postback", "_handle_status_update", "_handle_confirmation"):
        def mk(n):
            def _f(*a, **k): handlers_seen.append(n)
            return _f
        setattr(agent, name, mk(name))
    agent._on_message(payload)


# ── 1. 真值解析 ────────────────────────────────────────────────────────────
print("\n[1] CHAT_ENABLED 解析")
for val, expect in [(None, False), ("", False), ("ture", False), ("enabled", False),
                    ("false", False), ("0", False), ("off", False),
                    ("1", True), ("true", True), ("TRUE", True), (" true ", True),
                    ("yes", True), ("on", True)]:
    cs = load(val)
    check(f"CHAT_ENABLED={val!r} → {expect}", cs.CHAT_ENABLED is expect, f"got {cs.CHAT_ENABLED}")

# ── 2. 關閉時：一般文字 → 固定引導訊息，零副作用 ─────────────────────────────
print("\n[2] 關閉時的一般文字訊息")
cs = load(None)
agent, calls = make_agent(cs)
seen, forwarded, done = [], [], __import__("threading").Event()
route(agent, cs, {"user_id": "U" + "x" * 32, "text": "請問我家工程進度到哪了？", "reply_token": "RT1"},
      seen, forwarded, done)
done.wait(3)
pub = agent.broker.published
check("只送出一則訊息", len(pub) == 1, str(pub))
check("走 gateway/outbox", pub and pub[0][0] == cs.OUTBOX_TOPIC, str(pub[:1]))
check("內容為固定引導訊息", pub and pub[0][1].get("content") == cs.CHAT_DISABLED_NOTICE)
check("帶 reply_token（免費 Reply）", pub and pub[0][1].get("reply_token") == "RT1")
check("未進入 _process（Claude loop）", "_process" not in seen, str(seen))
check("未呼叫 Anthropic", calls["claude"] == 0)
check("未寫入記憶", calls["memory"] == 0)
check("未 publish trello 請求", all(t != cs.TRELLO_REQUEST_TOPIC for t, _ in pub))
check("引導訊息含三個功能名稱",
      all(k in cs.CHAT_DISABLED_NOTICE for k in ("今日提醒", "未來工項", "使用說明")))
check("引導訊息說明已轉交專人", "已轉交專人" in cs.CHAT_DISABLED_NOTICE)
check("原文轉發主管（1 次，含原文與來源）",
      forwarded == [("U" + "x" * 32, "請問我家工程進度到哪了？", None)], str(forwarded))

# ── 3. 關閉時：保留的關鍵字入口 ──────────────────────────────────────────────
print("\n[3] 關閉時的關鍵字備援")
for text, expect in [("使用說明", "_handle_guide"), ("help", "_handle_guide"),
                     ("今日提醒", "_handle_daily"), ("今天工程提醒", "_handle_daily"),
                     ("未來兩週工項", "_handle_future"), ("未來工項", "_handle_future"),
                     ("過去1月工項", "_handle_future")]:
    agent, _ = make_agent(cs)
    seen, fwd = [], []
    route(agent, cs, {"user_id": "U1", "text": text, "reply_token": "RT"}, seen, fwd)
    check(f"「{text}」→ {expect}（且不轉發主管）",
          seen == [expect] and not agent.broker.published and not fwd, f"seen={seen} fwd={fwd}")

# ── 4. 關閉時：postback 全部保留 ─────────────────────────────────────────────
print("\n[4] 關閉時的 postback 路由")
for op in ("daily", "future", "guide", "someday", "complete", "incomplete", "confirm", "reject"):
    agent, _ = make_agent(cs)
    seen = []
    route(agent, cs, {"user_id": "U1", "kind": "postback", "postback": {"o": op}, "reply_token": "RT"}, seen)
    check(f"postback o={op} → _process_postback", seen == ["_process_postback"], f"seen={seen}")

# postback dispatcher 內部分派（用真的 _process_postback，換掉下游 handler）
print("\n[4b] _process_postback 內部分派（關閉時）")
for op, target in [("daily", "_handle_daily"), ("someday", "_handle_daily"),
                   ("future", "_handle_future"), ("guide", "_handle_guide"),
                   ("complete", "_handle_status_update"), ("incomplete", "_handle_status_update"),
                   ("confirm", "_handle_confirmation"), ("reject", "_handle_confirmation")]:
    agent, _ = make_agent(cs)
    seen = []
    for name in ("_handle_guide", "_handle_daily", "_handle_future",
                 "_handle_status_update", "_handle_confirmation"):
        def mk(n):
            def _f(*a, **k): seen.append(n)
            return _f
        setattr(agent, name, mk(name))
    agent._process_postback("U1", {"o": op}, "RT")
    check(f"o={op} → {target}", seen == [target], f"seen={seen}")

# ── 5. 開啟時：恢復路徑未被破壞 ─────────────────────────────────────────────
print("\n[5] CHAT_ENABLED=true 的恢復路徑")
cs2 = load("true")
agent, _ = make_agent(cs2)
seen = []
fwd = []
route(agent, cs2, {"user_id": "U1", "text": "請問我家工程進度到哪了？", "reply_token": "RT"}, seen, fwd)
check("進入 _process（Claude loop）", seen == ["_process"], f"seen={seen}")
check("未送出引導訊息", not agent.broker.published, str(agent.broker.published))
check("未轉發主管（對話開啟時走 escalate 而非轉發）", not fwd, str(fwd))

# ── 6. 轉發主管群組的內容與去回音 ──────────────────────────────────────────
print("\n[6] _forward_offline_message")
cs = load(None)
import trello_line_notifier as tln

def fwd_case(group_id, notify_group, contacts=None):
    agent, _ = make_agent(cs)
    agent._user_identity = lambda uid: ("王小明", "小明", "customer")
    sent = []
    cs.send_line = lambda uid, msg: sent.append((uid, msg))
    cs.LINE_NOTIFY_GROUP_ID = notify_group
    if contacts is not None:
        tln.load_contacts = lambda: contacts
    agent._forward_offline_message("U" + "y" * 32, "浴室磁磚什麼時候貼？", group_id)
    return sent

sent = fwd_case(None, "Cnotify")
check("一對一來訊 → 轉發到通知群", len(sent) == 1 and sent[0][0] == "Cnotify", str(sent))
check("內容含原文", sent and "浴室磁磚什麼時候貼？" in sent[0][1])
check("內容含來源身分", sent and "王小明（小明）／customer" in sent[0][1], str(sent[:1]))
check("內容標記一對一", sent and "一對一" in sent[0][1])

sent = fwd_case("Cnotify", "Cnotify")
check("來自通知群本身 → 不轉發（避免回音）", sent == [], str(sent))

sent = fwd_case("Cother", "Cnotify")
check("其他群組來訊 → 轉發並標記群組", len(sent) == 1 and "群組" in sent[0][1], str(sent))

sent = fwd_case(None, "", contacts={"sa": "Usa", "larry": "Ularry"})
check("未設通知群 → 回退 sa/larry 個人",
      [u for u, _ in sent] == ["Usa", "Ularry"], str([u for u, _ in sent]))

# ── 7. gateway 透傳 group_id ────────────────────────────────────────────────
print("\n[7] gateway 把 group_id 帶進 inbox payload")
os.environ["LINE_CHANNEL_SECRET"] = ""      # 跳過驗簽（僅測 payload 組裝）
for m in [m for m in list(sys.modules) if m.startswith("gateway")]:
    del sys.modules[m]
gw = importlib.import_module("gateway.line_gateway")
published = []
gw.broker.publish = lambda topic, payload: published.append((topic, payload))
gw._upsert_line_user = lambda uid: None
client = gw.app.test_client()

def post(event):
    published.clear()
    r = client.post("/webhook", json={"events": [event]})
    return r.status_code, list(published)

sc, pubs = post({"type": "message", "source": {"type": "group", "groupId": "Cgrp", "userId": "U1"},
                 "message": {"type": "text", "text": "嗨"}, "replyToken": "RT"})
check("群組訊息帶 group_id", sc == 200 and pubs and pubs[0][1].get("group_id") == "Cgrp", str(pubs))
sc, pubs = post({"type": "message", "source": {"type": "user", "userId": "U1"},
                 "message": {"type": "text", "text": "嗨"}, "replyToken": "RT"})
check("一對一訊息 group_id 為 None", sc == 200 and pubs and pubs[0][1].get("group_id") is None, str(pubs))
sc, pubs = post({"type": "message", "source": {"type": "room", "roomId": "Rroom", "userId": "U1"},
                 "message": {"type": "text", "text": "嗨"}, "replyToken": "RT"})
check("聊天室訊息帶 roomId", sc == 200 and pubs and pubs[0][1].get("group_id") == "Rroom", str(pubs))

print("\n" + ("ALL PASS" if not FAILS else f"FAILED: {FAILS}"))
sys.exit(1 if FAILS else 0)
