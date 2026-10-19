"""smoke: 驗證工項定義（spec work-item-tag）——文字標記與 Trello 原生日期兩種寫法。

真的載入 trello_line_notifier / gantt_generator / customer_service，只把外部副作用
（Trello 抓取、DB 查詢、公司帳號查詢）換成固定資料。卡片資料照 2026-10-19 量到的
Trello 回傳形狀（`108.[人造石@(石凱)] 施工` 那張示範卡）。

行為檢查（run_checks / 未來工項 / 甘特 / ✅完成目標比對）只透過既有公開入口呼叫，
所以同一支測試拿舊程式碼跑也能執行——原生寫法的 case 應該失敗。

跑法：python3 tests/smoke_work_item_tag.py
"""
import os, sys, json, importlib
from datetime import date, time

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

import trello_line_notifier as tln

COMPANY = "66f123294afc4db9701158e2"   # jiahdoper（token 擁有者）
GHOST = "69f46e8af8d92446166bb05b"     # 量到會 404 的失效成員

def item(iid, name, due=None, member=None, state="incomplete"):
    return {"id": iid, "name": name, "due": due, "idMember": member, "state": state}

# 示範卡：卡片 11/02–11/03 17:00；三個待辦項（繼承石凱／公司／無日期）
CARD_108 = {
    "id": "C108", "name": "108.[人造石@(石凱)] 施工", "idList": "L_RUN",
    "start": "2026-11-02T00:00:00.000Z", "due": "2026-11-03T09:00:00.000Z", "dueComplete": False,
    "desc": "[@(石凱),20261102-20261104] 施工", "dateLastActivity": "2026-10-19T13:40:16.760Z",
    "checklists": [{"checkItems": [
        item("I1", "丈量 (系統櫃立好後）", due="2026-10-21T06:00:00.000Z"),
        item("I2", "下坎水槽寄送到廠商預先安裝", due="2026-10-23T06:00:00.000Z", member=COMPANY),
        item("I3", "現場附帶安裝品先準備 (水龍頭, 瓦斯爐, 電磁爐, 檯面垃圾桶,...)"),
    ]}],
}
# 名稱有 @ 但沒日期（錯誤設定）；卡內待辦項仍繼承
CARD_NODATE = {
    "id": "C170", "name": "170. [木地板@(板沐品)] 施工", "idList": "L_RUN",
    "start": None, "due": None, "dueComplete": False, "desc": "",
    "dateLastActivity": "2026-10-26T00:00:00.000Z",
    "checklists": [{"checkItems": [item("I4", "地板進料", due="2026-10-28T06:00:00.000Z")]}],
}
# 同樣沒日期但已完成 → 不列入警告
CARD_NODATE_DONE = dict(CARD_NODATE, id="C171", name="171. [油漆@(油劉)] 修補", dueComplete=True, checklists=[])
# 沒有卡片負責人：有 due、未指派的待辦項 → 不是工項
CARD_NOOWNER = {
    "id": "C200", "name": "200. 雜項", "idList": "L_RUN", "start": None, "due": None,
    "dueComplete": False, "desc": "", "dateLastActivity": "2026-10-26T00:00:00.000Z",
    "checklists": [{"checkItems": [item("I5", "清潔", due="2026-10-28T06:00:00.000Z")]}],
}
# 失效成員 → 退回卡片負責人；文字標記待辦項不受 due／指派影響；全部完成 → #8
CARD_MIX = {
    "id": "C300", "name": "300.[水電@(阿明)@(阿華)] 配管", "idList": "L_RUN",
    "start": None, "due": "2026-10-30T09:00:00.000Z", "dueComplete": False, "desc": "",
    "dateLastActivity": "2026-10-26T00:00:00.000Z",
    "checklists": [{"checkItems": [
        item("I6", "配管", due="2026-10-29T06:00:00.000Z", member=GHOST, state="complete"),
        item("I7", "[@(石凱),20261025-20261025:1400] 丈量", due="2026-12-01T06:00:00.000Z",
             member=COMPANY, state="complete"),
    ]}],
}
# 舊寫法：名稱沒有 @、描述第一行文字標記
CARD_LEGACY = {
    "id": "C400", "name": "400. 防水", "idList": "L_RUN", "start": None, "due": None,
    "dueComplete": False, "desc": "[@(Larry)@(SA),-20261030] 防水層施工驗收",
    "dateLastActivity": "2026-10-26T00:00:00.000Z", "checklists": [],
}
BOARD = {"id": "B1", "name": "竹北王宅", "lists": {"L_RUN": "執行中"},
         "cards": [CARD_108, CARD_NODATE, CARD_NODATE_DONE, CARD_NOOWNER, CARD_MIX, CARD_LEGACY]}

CONTACTS = {"石凱": "U_SHIKAI", "板沐品": "U_BAN", "阿明": "U_MING", "阿華": "U_HUA",
            "larry": "U_LARRY", "sa": "U_SA"}
ADMIN = "U_ADMIN"
AS_OF = date(2026, 10, 27)

tln._scan_boards = lambda: [BOARD]
tln._internal_recipients = lambda: [ADMIN]
tln.load_contacts = lambda: dict(CONTACTS)
tln._resolve_tag_recipients = lambda names, **k: [CONTACTS[n] for n in names if n in CONTACTS]
tln._all_project_names = lambda: {"B1": "竹北-系統櫃"}
tln._pending_confirmations = lambda: []
tln._valid_aliases = lambda: None
tln.company_member_id = lambda: COMPANY
tln.today_tw = lambda: date(2026, 10, 20)

# ── 1. 解析入口（新函式；舊程式碼沒有 → 整段 FAIL）──
try:
    wc, wi_ = tln.work_item_of_card, tln.work_item_of_checkitem
    w = wc(CARD_108)
    check("原生卡：負責人取名稱 @", w and w["names"] == ["石凱"], w)
    check("原生卡：Trello 日期（台北）", w and (w["start"], w["end"], w["end_time"]) == (date(2026, 11, 2), date(2026, 11, 3), time(17, 0)), w)
    check("原生卡：說明去掉 @", w and w["label"] == "108.[人造石] 施工", w and w["label"])
    check("過渡期卡：Trello 日期優先於描述標記", w and w["end"] == date(2026, 11, 3) and w["source"] == "card_native")
    its = CARD_108["checklists"][0]["checkItems"]
    a, b, c = (wi_(x, CARD_108) for x in its)
    check("待辦項繼承卡片負責人", a and a["names"] == ["石凱"] and a["end"] == date(2026, 10, 21) and a["start"] is None, a)
    check("待辦項 due 時間（台北 14:00）", a and a["end_time"] == time(14, 0), a and a["end_time"])
    check("指派公司帳號 → 公司負責", b and b["company"] and b["names"] == [], b)
    check("沒有日期的待辦項 → 不是工項", c is None, c)
    check("名稱有 @ 沒日期 → 卡片本身不是工項", wc(CARD_NODATE) is None)
    check("名稱有 @ 沒日期 → 列為錯誤設定", tln.card_owner_missing_dates(CARD_NODATE))
    d = wi_(CARD_NODATE["checklists"][0]["checkItems"][0], CARD_NODATE)
    check("錯誤設定卡的待辦項仍繼承", d and d["names"] == ["板沐品"], d)
    check("卡片無負責人＋未指派 → 不是工項", wi_(CARD_NOOWNER["checklists"][0]["checkItems"][0], CARD_NOOWNER) is None)
    m = wc(CARD_MIX)
    check("多位負責人", m and m["names"] == ["阿明", "阿華"], m)
    check("只有到期日的卡片 → start=None", m and m["start"] is None and m["end"] == date(2026, 10, 30), m)
    g = wi_(CARD_MIX["checklists"][0]["checkItems"][0], CARD_MIX)
    check("非公司帳號的指派 → 退回卡片負責人", g and g["names"] == ["阿明", "阿華"] and not g["company"], g)
    t = wi_(CARD_MIX["checklists"][0]["checkItems"][1], CARD_MIX)
    check("文字標記待辦項不受 due／指派影響", t and t["names"] == ["石凱"] and t["end"] == date(2026, 10, 25) and not t["company"], t)
    lg = wc(CARD_LEGACY)
    check("舊寫法描述標記照舊", lg and lg["names"] == ["larry", "sa"] and lg["source"] == "card_desc", lg)
    tln.company_member_id = lambda: None
    check("公司帳號查不到 → 指派的待辦項 fail-closed", wi_(its[1], CARD_108) is None)
    check("公司帳號查不到 → 未指派的照常繼承", wi_(its[0], CARD_108) is not None)
    tln.company_member_id = lambda: COMPANY
except AttributeError as e:
    check("解析入口存在", False, e)

# ── 2. 每日通知 run_checks（基準日 10/27）──
notes = tln.run_checks(as_of=AS_OF)
def heads(uid):
    return [(r[2], r[3]) for u, _, r in notes if u == uid and r[0] == "item"]
def summary(uid):
    return next((r for u, b, r in notes if u == uid and b == "__summary__"), None)
sk = heads("U_SHIKAI")
check("石凱：原生卡 6 天後開始（#1）", ("6 天後開始", "執行中/108.[人造石@(石凱)] 施工") in sk, sk)
check("石凱：繼承的『丈量』已逾期（#6）", any(h.startswith("已逾期 6 天") for h, _ in sk), sk)
check("石凱：收不到公司負責的『下坎水槽』", not any("逾期 4 天" in h for h, _ in sk), sk)
ad = heads(ADMIN)
check("主管：收到公司負責的『下坎水槽』逾期", any(h == "已逾期 4 天" for h, _ in ad), ad)
check("無負責人的待辦項不產生通知", not any(r[4].endswith("清潔") for _, _, r in notes if r[0] == "item"))
check("#8 全部完成 → 卡片負責人", ("所有工項已全部完成 ✓", "執行中/300.[水電@(阿明)@(阿華)] 配管") in heads("U_MING"), heads("U_MING"))
sa = summary(ADMIN)
warn = dict(sa[3]) if sa else {}
wkey = next((k for k in warn if "未設日期" in k), None)
check("主管摘要：『已指定負責人但未設日期』警告", wkey is not None, list(warn))
check("警告列出錯誤設定卡（公開標籤/列表/卡片）", wkey and "・竹北-系統櫃/執行中/170. [木地板@(板沐品)] 施工" in warn[wkey], wkey and warn[wkey])
check("已完成的卡不列入警告", wkey and not any("171." in s for s in warn[wkey]))
sb = summary("U_BAN")
check("廠商摘要不含設定警告", sb is None or not any("未設日期" in k for k, _ in sb[3]), sb and sb[3])

# ── 3. 未來工項（today 10/20，未來 14 天；石凱／主管）──
def future_text(owner):
    msgs = tln.build_future_messages_for_user("future", 14, None, owner)
    return json.dumps(msgs, ensure_ascii=False)
fs = future_text("石凱")
check("未來工項：石凱看得到繼承的『丈量』", "丈量 (系統櫃立好後）" in fs)
check("未來工項：石凱看不到公司的『下坎水槽』", "下坎水槽" not in fs)
fa = future_text(None)
check("未來工項：主管看到『下坎水槽』標 @公司", "@公司" in fa and "下坎水槽" in fa)

# ── 4. ✅完成目標比對（customer_service._resolve_target）──
cs = importlib.import_module("agents.customer_service")
rt = cs.CustomerServiceAgent._resolve_target
names, label, done = rt(None, CARD_108, "checklist", "I1")
check("✅完成：繼承的待辦項負責人為石凱", names == ["石凱"], (names, label))
names, label, done = rt(None, CARD_108, "checklist", "I2")
check("✅完成：公司的待辦項不屬於石凱", names is not None and "石凱" not in names, (names, label))
names, label, done = rt(None, CARD_108, "card", None)
check("✅完成：原生卡負責人與說明", names == ["石凱"] and label == "108.[人造石] 施工", (names, label))

# ── 5. 甘特 CSV（gantt_generator.collect_items）──
gg = importlib.import_module("gantt_generator")
gg.get_boards = lambda: [{"id": "B1", "name": "竹北王宅"}]
gg.get_lists = lambda bid: {"L_RUN": "執行中"}
gg.get_cards = lambda bid: BOARD["cards"]
gg._valid_aliases = lambda: None
rows = {r["label"]: r for r in gg.collect_items()}
check("甘特：原生卡列", "108.[人造石] 施工" in rows and rows["108.[人造石] 施工"]["end"] == date(2026, 11, 3), list(rows))
check("甘特：公司列負責人為「公司」", rows.get("下坎水槽寄送到廠商預先安裝", {}).get("names") == "公司", rows.get("下坎水槽寄送到廠商預先安裝"))
check("甘特：無日期待辦項不出現", not any(k.startswith("現場附帶") for k in rows))

print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAIL: {FAILS}")
sys.exit(1 if FAILS else 0)
