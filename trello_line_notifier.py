#!/usr/bin/env python3
import os
import json
import re
import requests
import sys
from datetime import date, datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
LINE_API = "https://api.line.me/v2/bot/message/push"
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
TRELLO_KEY = os.environ.get("TRELLO_API_KEY", "")
TRELLO_TOKEN = os.environ.get("TRELLO_TOKEN", "")
WORKSPACE_ID = "jiahomedesign1"

_KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "knowledge")
CONTACTS_FILE = os.path.join(_KNOWLEDGE_DIR, "contacts.json")

sys.path.insert(0, os.path.dirname(__file__))
try:
    from shared.db import db_exec as _db_exec
except ImportError:
    _db_exec = None

# mode → 負責的條件
# morning : #2 今日開始、#4 今日到期（時間未到）、#9 每日摘要
# noon    : #1 開始倒數、#3 結束倒數、#7 停滯、#8 全完成
# evening : #5 今日已逾期、#6 結束日已過期（weekday only）

# notifications 格式：(uid, board_name, item_text)
# board_name = "__summary__" 為每日摘要，不分組



# per-run 收集器：未對應的 Trello alias -> 出處集合（"board/card"）。run_checks() 起始清空。
_unresolved_aliases: dict[str, set[str]] = {}

# per-run 收集器：所有檢查項皆完成、但卡片不在「已完成」欄的 "board/card"。morning render。
_complete_unfiled: list[str] = []


def _resolve_tag_recipients(names: list[str], source: str | None = None) -> list[str]:
    """Resolve Trello tag names to LINE IDs via alias_name DB lookup.

    未對應的名字除了印 log，也累積到 _unresolved_aliases（含可選出處 source），
    供 morning 每日摘要呈現給 SA/Larry。
    """
    if not names or _db_exec is None:
        return []
    def _query(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT alias_name, line_id FROM line_users WHERE alias_name = ANY(%s)",
                (names,),
            )
            return {row[0]: row[1] for row in cur.fetchall()}
    mapping = _db_exec(_query) or {}
    result = []
    for n in names:
        if n in mapping:
            result.append(mapping[n])
        else:
            print(f"[notifier] WARNING: alias not found: {n}")
            srcs = _unresolved_aliases.setdefault(n, set())
            if source:
                srcs.add(source)
    return result


def _resolve_recipients_by_board_id(board_id: str) -> list[str]:
    """Resolve LINE IDs for all users assigned to the project with this Trello board_id."""
    if not board_id or _db_exec is None:
        return []
    def _query(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT lup.line_id FROM line_user_projects lup "
                "JOIN projects p ON p.project_id = lup.project_id "
                "WHERE p.trello_board_id = %s AND p.status = 'active'",
                (board_id,),
            )
            return [row[0] for row in cur.fetchall()]
    result = _db_exec(_query) or []
    if not result:
        print(f"[notifier] WARNING: no recipients for board_id: {board_id}")
    return result


def _internal_recipients() -> list[str]:
    """所有管理者/員工的 LINE IDs — 內部提醒（#3–#7、#9）的收件人。

    取代舊有固定的 sa/larry 兩個 alias。DB 不可用或查無時回 []（內部份該次不送，僅 log）。
    """
    if _db_exec is None:
        return []
    def _query(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT line_id FROM line_users WHERE role IN ('admin', 'employee')"
            )
            return [row[0] for row in cur.fetchall()]
    result = _db_exec(_query) or []
    if not result:
        print("[notifier] WARNING: no internal recipients (admin/employee) found")
    return result


def _load_contacts_from_db() -> dict | None:
    if _db_exec is None:
        return None
    def _query(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT line_id, display_name FROM line_users "
                "WHERE role IN ('admin', 'employee', 'vendor', 'customer')"
            )
            return cur.fetchall()
    rows = _db_exec(_query)
    if rows is None:
        return None
    result = {}
    for row in rows:
        if isinstance(row, dict):
            line_id, name = row["line_id"], row["display_name"] or row["line_id"]
        else:
            line_id, name = row[0], row[1] or row[0]
        result[name.lower()] = line_id
    return result


def load_contacts() -> dict:
    """Return {name_lower: line_id} from DB; falls back to contacts.json on error."""
    try:
        result = _load_contacts_from_db()
        if result is not None:
            return result
    except Exception as e:
        print(f"[notifier] WARNING: DB load_contacts failed: {e}, falling back to file")
    try:
        with open(CONTACTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        return {}
    result = {}
    for k, v in data.items():
        if k.startswith("備"):
            continue
        line_id = v.get("line_id", "") if isinstance(v, dict) else v
        if line_id:
            result[k.lower()] = line_id
    return result


def send_line(user_id, message):
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {
        "to": user_id,
        "messages": [{"type": "text", "text": message}],
    }
    resp = requests.post(LINE_API, headers=headers, json=body)
    return resp.status_code, resp.text


def send_flex(user_id, contents, alt_text):
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {
        "to": user_id,
        "messages": [{"type": "flex", "altText": alt_text[:400], "contents": contents}],
    }
    resp = requests.post(LINE_API, headers=headers, json=body)
    return resp.status_code, resp.text


# 到期急迫度 → 文字顏色（越急越紅）
def _due_color(days):
    if days <= 1:
        return "#D32F2F"   # 紅：今天/明天
    if days <= 3:
        return "#EF6C00"   # 橙
    return "#C79100"       # 琥珀：4–7 天


def get_boards():
    url = f"https://api.trello.com/1/organizations/{WORKSPACE_ID}/boards"
    params = {"key": TRELLO_KEY, "token": TRELLO_TOKEN, "filter": "open"}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def get_lists(board_id):
    url = f"https://api.trello.com/1/boards/{board_id}/lists"
    params = {"key": TRELLO_KEY, "token": TRELLO_TOKEN, "fields": "name"}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return {lst["id"]: lst["name"] for lst in resp.json()}


def get_cards(board_id):
    url = f"https://api.trello.com/1/boards/{board_id}/cards"
    params = {
        "key": TRELLO_KEY,
        "token": TRELLO_TOKEN,
        "checklists": "all",
        "fields": "name,desc,dateLastActivity,idList,dueComplete",
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def get_card(card_id):
    """Fetch one card with its checklists (for owner re-validation on write)."""
    url = f"https://api.trello.com/1/cards/{card_id}"
    params = {
        "key": TRELLO_KEY, "token": TRELLO_TOKEN,
        "checklists": "all", "fields": "name,desc,idBoard,idList,dueComplete",
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


# ── Trello 寫入（完成狀態 + 稽核留言）─────────────────────────────────────────

def _trello_auth():
    return {"key": TRELLO_KEY, "token": TRELLO_TOKEN}


def set_checkitem_state(card_id, checkitem_id, complete: bool):
    """PUT checkItem state. Returns (status_code, ok)."""
    url = f"https://api.trello.com/1/cards/{card_id}/checkItem/{checkitem_id}"
    params = {**_trello_auth(), "state": "complete" if complete else "incomplete"}
    resp = requests.put(url, params=params)
    return resp.status_code, resp.ok


def set_card_due_complete(card_id, complete: bool):
    """PUT card.dueComplete. Returns (status_code, ok)."""
    url = f"https://api.trello.com/1/cards/{card_id}"
    params = {**_trello_auth(), "dueComplete": "true" if complete else "false"}
    resp = requests.put(url, params=params)
    return resp.status_code, resp.ok


def add_card_comment(card_id, text: str):
    """POST a comment to the card's activity feed (留言與活動). Returns (status_code, ok)."""
    url = f"https://api.trello.com/1/cards/{card_id}/actions/comments"
    params = {**_trello_auth(), "text": text[:16000]}
    resp = requests.post(url, params=params)
    return resp.status_code, resp.ok


def get_board_full(board_id: str) -> dict:
    """Single call: returns {id, name, lists: {id: name}, cards: [...]} for one board."""
    url = f"https://api.trello.com/1/boards/{board_id}"
    params = {
        "key": TRELLO_KEY,
        "token": TRELLO_TOKEN,
        "lists": "open",
        "list_fields": "name",
        "cards": "open",
        "card_fields": "name,desc,dateLastActivity,idList,dueComplete",
        "checklists": "all",
        "checklist_fields": "name,idCard",
        "fields": "name",
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    cl_map: dict[str, list] = {}
    for cl in data.get("checklists", []):
        cl_map.setdefault(cl["idCard"], []).append(cl)
    for card in data.get("cards", []):
        card["checklists"] = cl_map.get(card["id"], [])
    return {
        "id": board_id,
        "name": data.get("name", board_id),
        "lists": {lst["id"]: lst["name"] for lst in data.get("lists", [])},
        "cards": data.get("cards", []),
    }


def get_boards_batch(board_ids: list[str], max_workers: int = 10) -> list[dict]:
    """Fetch multiple boards concurrently. Trello /1/batch doesn't support
    complex nested query params, so we use a thread pool instead."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(board_ids))) as pool:
        futures = {pool.submit(get_board_full, bid): bid for bid in board_ids}
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception:
                pass
    return results


ITEM_RE = re.compile(
    r"\[@((?:@?\([^)]+\))+),\s*(\d{8})?-?(\d{8})?(?::(\d{4}))?\](.*)"
)
NAME_RE = re.compile(r"\(([^)]+)\)")


def parse_tag(text):
    """回傳 (names[], start_date, end_date, end_time, label) 或 None"""
    m = ITEM_RE.match(text.strip())
    if not m:
        return None
    names = [n.lower() for n in NAME_RE.findall(m.group(1))]
    start = datetime.strptime(m.group(2), "%Y%m%d").date() if m.group(2) else None
    end = datetime.strptime(m.group(3), "%Y%m%d").date() if m.group(3) else None
    end_time = datetime.strptime(m.group(4), "%H%M").time() if m.group(4) else None
    label = m.group(5).strip()
    return names, start, end, end_time, label


def days_diff(d):
    return (d - date.today()).days


def _summary_window(start, end):
    """以 ±7 補出缺的端點，回傳完整 (start, end)：

    - 都有：原樣 (start, end)
    - 只有 end（-YYYYMMDD）：(end-7, end)
    - 只有 start（YYYYMMDD-）：(start, start+7)
    - 都無：(None, None)
    """
    if start and end:
        return start, end
    if end:
        return end - timedelta(days=7), end
    if start:
        return start, start + timedelta(days=7)
    return None, None


def _in_summary(start, end, is_complete) -> bool:
    """#9 每日摘要納入條件：尚未完成，且今天已到補完窗口的起點（今天 >= 補出的 start）。

    無上界：逾期未完成的工項持續顯示，直到打勾完成。未來（今天 < start）與已完成→排除。
    """
    if is_complete:
        return False
    ns, _ = _summary_window(start, end)
    return ns is not None and days_diff(ns) <= 0


def _summary_overdue(start, end) -> bool:
    """今天已過補完窗口的終點（今天 > 補出的 end）→ 在摘要標「逾期」。"""
    _, ne = _summary_window(start, end)
    return ne is not None and days_diff(ne) < 0


def fmt_item(list_name, card_name, body):
    """格式化單項通知（不含 board name）"""
    return f"【{list_name}/{card_name}】\n{body}"


def check_item(names, start, end, end_time, label, contacts, board_name, list_name, card_name, raw, notifications, internal, is_complete: bool = False,
               board_id="", card_id="", checkitem_id=None, source="card"):
    sponsors = _resolve_tag_recipients(names, source=f"{board_name}/{card_name}") or [contacts[n] for n in names if n in contacts]
    sub = f"{list_name}/{card_name}"
    # #3~#6 共用前提：載體未完成（card dueComplete / checklist state）才發送
    # → 打勾完成的工項不再收到到期/逾期通知（#1/#2 開始日不受此限；清單名稱不當抑制）
    active = not is_complete

    # 一筆通知 = ("item", 顏色, 抬頭, 子標題, 原始文字, board_id, card_id, checkitem_id, source)
    # 後四欄供提醒卡片的「標記完成/取消」postback 按鈕定位目標工項。
    def add(uids, headline, color):
        rec = ("item", color, headline, sub, raw, board_id, card_id, checkitem_id, source)
        for uid in uids:
            notifications.append((uid, board_name, rec))

    # 單一每日批次：一次評估全部觸發條件（原 morning/noon/evening 合併）。
    # #2 今日開始
    if start and days_diff(start) == 0:
        add(sponsors, "今日開始", "#388E3C")
    # #1 開始倒數（1–7 天後）
    if start and 1 <= days_diff(start) <= 7:
        add(sponsors, f"{days_diff(start)} 天後開始", "#1976D2")
    # #4 今日到期（#5「今日時間已過」在清晨每日批次視為惰性，由本條涵蓋）
    if active and end and days_diff(end) == 0:
        time_str = f"（{end_time.strftime('%H:%M')}）" if end_time else ""
        add(set(sponsors + internal), f"今日{time_str}到期", "#D32F2F")
    # #3 結束倒數（1–7 天內）
    if active and end and 1 <= days_diff(end) <= 7:
        d = days_diff(end)
        add(set(sponsors + internal), f"{d} 天內到期", _due_color(d))
    # #6 已逾期（所有執行日皆呈現；批次排程 Sun–Fri，週六不跑）
    if active and end and days_diff(end) < 0:
        add(set(sponsors + internal), f"已逾期 {abs(days_diff(end))} 天", "#B71C1C")


def _inactive_board_ids() -> set:
    """Trello board_ids whose project is completed or archived — skip in notifier."""
    if _db_exec is None:
        return set()
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT trello_board_id FROM projects "
                "WHERE trello_board_id IS NOT NULL AND status IN ('completed','archived')"
            )
            return {row[0] for row in cur.fetchall()}
    return _db_exec(_q) or set()


def _pending_confirmations() -> list:
    """待主管追認的廠商暫定變更（task_confirmations status=pending）。
    回傳含定位資訊：id(cid)、board_id、card_name、label、target_state、claimer_alias、claimer_display。
    供主管的每日內容以可操作確認卡呈現。"""
    if _db_exec is None:
        return []
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tc.id, tc.board_id, tc.card_name, tc.label, tc.target_state, "
                "tc.claimer_alias, lu.display_name AS claimer_display "
                "FROM task_confirmations tc "
                "LEFT JOIN line_users lu ON lu.line_id = tc.claimer_user_id "
                "WHERE tc.status = 'pending' ORDER BY tc.claimed_at"
            )
            return cur.fetchall()
    return _db_exec(_q) or []


def _all_project_names() -> dict:
    """{board_id: project_name} for all projects with a Trello board (含已完成/封存，
    供確認卡定位；查無時由呼叫端以後備值呈現）。"""
    if _db_exec is None:
        return {}
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT trello_board_id, name FROM projects WHERE trello_board_id IS NOT NULL"
            )
            return {row[0]: row[1] for row in cur.fetchall()}
    return _db_exec(_q) or {}


def _roles_by_lineid(uids: list[str]) -> dict:
    """{line_id: role} for the given LINE ids — used to限定主動 push 僅送 vendor。"""
    if not uids or _db_exec is None:
        return {}
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT line_id, role FROM line_users WHERE line_id = ANY(%s)", (uids,)
            )
            return {row[0]: row[1] for row in cur.fetchall()}
    return _db_exec(_q) or {}


def run_checks():
    """單一每日批次：一次評估全部觸發條件（#1–#9），回傳 (uid, board_name, rec) 清單。
    主管(internal)額外得每日摘要與可操作確認卡。交付（push 過濾 / on-demand 拉取）由呼叫端決定。"""
    _unresolved_aliases.clear()
    _complete_unfiled.clear()
    contacts = load_contacts()
    internal = _internal_recipients()  # 所有管理者/員工 — #3–#7、#9 內部收件人
    boards = get_boards()
    skip_ids = _inactive_board_ids()
    notifications = []
    summary_items = []

    for board in boards:
        if board["id"] in skip_ids:
            print(f"[notifier] skip non-active project board: {board.get('name')}")
            continue
        board_name = board["name"]
        list_map = get_lists(board["id"])
        cards = get_cards(board["id"])
        for card in cards:
            list_name = list_map.get(card.get("idList", ""), "")
            card_has_check = False      # 此卡是否有帶標記的檢查項
            card_all_complete = True    # 其所有檢查項是否皆完成（打勾）

            if card.get("desc"):
                first_line = card["desc"].split("\n")[0]
                parsed = parse_tag(first_line)
                if parsed:
                    card_has_check = True
                    is_complete = bool(card.get("dueComplete"))
                    if not is_complete:
                        card_all_complete = False
                    names, start, end, end_time, label = parsed
                    if not label:
                        label = card["name"]
                    check_item(names, start, end, end_time, label, contacts, board_name, list_name, card["name"], first_line.strip(), notifications, internal, is_complete=is_complete,
                               board_id=board["id"], card_id=card["id"], checkitem_id=None, source="card")
                    if _in_summary(start, end, is_complete):
                        summary_items.append((board_name, list_name, card["name"], label, _summary_overdue(start, end)))

            for checklist in card.get("checklists", []):
                items = checklist.get("checkItems", [])
                has_tag = False
                for item in items:
                    parsed = parse_tag(item["name"])
                    if not parsed:
                        continue
                    has_tag = True
                    card_has_check = True
                    is_complete = (item.get("state") == "complete")
                    if not is_complete:
                        card_all_complete = False
                    names, start, end, end_time, label = parsed
                    check_item(names, start, end, end_time, label, contacts, board_name, list_name, card["name"], item["name"].strip(), notifications, internal, is_complete=is_complete,
                               board_id=board["id"], card_id=card["id"], checkitem_id=item["id"], source="checklist")
                    if _in_summary(start, end, is_complete):
                        summary_items.append((board_name, list_name, card["name"], label, _summary_overdue(start, end)))

                if not has_tag:
                    continue

                # #7 停滯（內部）
                last_activity = card.get("dateLastActivity")
                if last_activity:
                    last_dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
                    days_stale = (datetime.now(TAIPEI) - last_dt.astimezone(TAIPEI)).days
                    incomplete = [i for i in items if i["state"] == "incomplete"]
                    if incomplete and days_stale >= 3:
                        rec = ("item", "#EF6C00", f"已停滯 {days_stale} 天，請追蹤", f"{list_name}/{card['name']}", "", "", "", None, "card")
                        for uid in internal:
                            if uid:
                                notifications.append((uid, board_name, rec))

                # #8 全部完成
                if items and all(i["state"] == "complete" for i in items):
                    for item in items:
                        parsed = parse_tag(item["name"])
                        if parsed:
                            names, _, _, _, _ = parsed
                            sponsors = [contacts[n] for n in names if n in contacts]
                            rec = ("item", "#388E3C", "所有工項已全部完成 ✓", f"{list_name}/{card['name']}", "", "", "", None, "card")
                            for uid in sponsors:
                                notifications.append((uid, board_name, rec))
                            break

            # 完成但未歸欄：整張卡所有檢查項皆完成、卻不在「已完成」欄 → minor 警告（morning render）
            if card_has_check and card_all_complete and "已完成" not in list_name:
                _complete_unfiled.append(f"{board_name}/{card['name']}")

    # #9 每日摘要（內部）— 結構化資料，由 build_flex 以與專案提醒同款的 bubble 呈現
    now_str = datetime.now(TAIPEI).strftime("%Y/%m/%d")
    # 巢狀結構：board → 狀態欄(list_name) → 卡片 → [工項]；收斂同卡重複、同工項去重
    from collections import OrderedDict
    tree = OrderedDict()
    for board, lst, card, label, overdue in summary_items:
        cards = tree.setdefault(board, OrderedDict()).setdefault(lst, OrderedDict())
        labels = cards.setdefault(card, [])
        entry = (label, overdue)
        if entry not in labels:
            labels.append(entry)

    def _status_rank(lst):
        if "已完成" in lst: return 2
        if "執行中" in lst: return 1
        if "未執行" in lst: return 0
        return 3

    sections = tuple(
        (
            board,
            tuple(
                (lst, tuple((card, tuple(labels)) for card, labels in cards.items()))
                for lst, cards in sorted(cols.items(), key=lambda kv: (_status_rank(kv[0]), kv[0]))
            ),
        )
        for board, cols in tree.items()
    )
    # warnings: ((標題, (行,...)),...)，各自一張 bubble（用 tuple 以保持 rec 可 hash 供去重）
    warnings = []
    if _unresolved_aliases:
        wlines = []
        for name in sorted(_unresolved_aliases):
            srcs = sorted(_unresolved_aliases[name])
            if srcs:
                shown = "、".join(srcs[:3])
                if len(srcs) > 3:
                    shown += f"…等 {len(srcs)} 處"
                wlines.append(f"・{name}（{shown}）")
            else:
                wlines.append(f"・{name}")
        warnings.append(("⚠️ 查無對應 LINE 帳號（未發送通知）", tuple(wlines)))
    if _complete_unfiled:
        warnings.append(("✅ 已完成但未歸『已完成』欄（請移動卡片）", tuple(f"・{s}" for s in _complete_unfiled)))
    summary_rec = ("summary", now_str, sections, tuple(warnings))
    # 摘要僅在有實際內容時附給內部（空摘要不佔 bubble；無內容主管→拉取時回「今日無提醒」）
    has_summary = bool(sections or warnings)
    for uid in internal:
        if not uid:
            continue
        if has_summary:
            notifications.append((uid, "__summary__", summary_rec))

    # 待主管確認 → 每筆一張可操作確認卡（取代舊摘要內的純文字清單）。
    # rec = ("confirm", cid, 專案名, 卡片名, label, who, act)
    pending = _pending_confirmations()
    if pending and internal:
        proj_map = _all_project_names()
        confirm_recs = []
        for row in pending:
            if isinstance(row, dict):
                cid, board_id, card_name = row["id"], row["board_id"], row.get("card_name")
                label = row["label"]; tstate = row["target_state"]
                alias = row.get("claimer_alias"); cdisplay = row.get("claimer_display")
            else:
                cid, board_id, card_name, label, tstate, alias, cdisplay = row
            project = proj_map.get(board_id) or "（未登錄專案）"
            act = "完成" if tstate == "complete" else "取消完成"
            if cdisplay and alias:
                who = f"{cdisplay}（{alias}）"
            else:
                who = cdisplay or alias or "廠商"
            confirm_recs.append(("confirm", cid, project, card_name or "", label, who, act))
        for uid in internal:
            if not uid:
                continue
            for rec in confirm_recs:
                notifications.append((uid, "__confirm__", rec))

    # 去除重複通知
    seen = set()
    unique = []
    for item in notifications:
        if item not in seen:
            seen.add(item)
            unique.append(item)

    # 凡通知 larry，也同步通知 larryoffice
    larry_ids = _resolve_tag_recipients(["larry"])
    larryoffice_ids = _resolve_tag_recipients(["larryoffice"])
    larry_uid = larry_ids[0] if larry_ids else contacts.get("larry")
    larryoffice_uid = larryoffice_ids[0] if larryoffice_ids else contacts.get("larryoffice")
    if larry_uid and larryoffice_uid:
        for uid, bn, it in list(unique):
            if uid == larry_uid:
                mirrored = (larryoffice_uid, bn, it)
                if mirrored not in seen:
                    seen.add(mirrored)
                    unique.append(mirrored)

    return unique


def _postback_data(op, board_id, card_id, checkitem_id, source):
    """編碼提醒按鈕 postback data（≤300 字元）。op=complete|incomplete；s=card|checklist。"""
    return f"o={op}&b={board_id}&c={card_id}&i={checkitem_id or ''}&s={source}"


def _status_buttons(board_id, card_id, checkitem_id, source):
    """提醒卡片上的「標記完成 / 取消完成」postback 按鈕列。"""
    return {
        "type": "box", "layout": "horizontal", "margin": "md", "spacing": "sm",
        "contents": [
            {"type": "button", "style": "primary", "color": "#388E3C", "height": "sm",
             "action": {"type": "postback", "label": "✅ 標記完成",
                        "data": _postback_data("complete", board_id, card_id, checkitem_id, source),
                        "displayText": "標記完成"}},
            {"type": "button", "style": "secondary", "height": "sm",
             "action": {"type": "postback", "label": "↩︎ 取消完成",
                        "data": _postback_data("incomplete", board_id, card_id, checkitem_id, source),
                        "displayText": "取消完成"}},
        ],
    }


def _confirm_bubble(rec):
    """待主管確認的可操作卡片：專案名＋卡片名＋label＋標記人＋確認/退回按鈕。
    rec = ("confirm", cid, 專案名, 卡片名, label, who, act)。"""
    _, cid, project, card_name, label, who, act = rec
    body = [{"type": "text", "text": project or "（未登錄專案）", "size": "xs", "color": "#1976D2", "wrap": True}]
    if card_name:
        body.append({"type": "text", "text": card_name, "size": "sm", "color": "#666666", "wrap": True, "margin": "xs"})
    body += [
        {"type": "separator", "margin": "md"},
        {"type": "text", "text": label, "weight": "bold", "size": "sm", "color": "#1A1A1A", "wrap": True, "margin": "md"},
        {"type": "text", "text": f"由 {who} 標記{act}", "size": "xs", "color": "#666666", "wrap": True, "margin": "sm"},
        {"type": "box", "layout": "horizontal", "margin": "lg", "spacing": "sm", "contents": [
            {"type": "button", "style": "primary", "color": "#388E3C", "height": "sm",
             "action": {"type": "postback", "label": "✅ 確認", "data": f"o=confirm&cid={cid}", "displayText": "確認"}},
            {"type": "button", "style": "secondary", "height": "sm",
             "action": {"type": "postback", "label": "↩︎ 退回", "data": f"o=reject&cid={cid}", "displayText": "退回"}},
        ]},
    ]
    return {
        "type": "bubble", "size": "mega",
        "header": {"type": "box", "layout": "vertical", "contents": [
            {"type": "text", "text": "意念情境・待主管確認", "size": "xs", "color": "#AAAAAA"},
            {"type": "text", "text": f"廠商標記{act}", "weight": "bold", "size": "md", "color": "#EF6C00", "margin": "sm"}]},
        "body": {"type": "box", "layout": "vertical", "contents": body},
    }


def build_flex(items, mode_label):
    """將同一收件人的 (board_name, rec) 清單組成 LINE Flex 訊息 contents。
    rec = ("item", 顏色, 抬頭, 子標題, 原始文字, board_id, card_id, checkitem_id, source)、("summary", …) 或 ("confirm", …)。
    確認卡優先；每個看板一張 bubble；到期狀態以彩色抬頭放最前面，下方完整保留原始 tag，附完成/取消按鈕。"""
    board_order = []
    by_board = {}
    summaries = []
    confirms = []
    for board_name, rec in items:
        if rec[0] == "summary":
            summaries.append(rec)
            continue
        if rec[0] == "confirm":
            confirms.append(rec)
            continue
        by_board.setdefault(board_name, [])
        if board_name not in board_order:
            board_order.append(board_name)
        by_board[board_name].append(rec)

    # 確認卡優先排在最前，避免 12 bubble 上限截斷時被丟棄
    bubbles = [_confirm_bubble(rec) for rec in confirms]
    for board in board_order:
        body = []
        for i, rec in enumerate(by_board[board]):
            color, headline, sub, raw = rec[1], rec[2], rec[3], rec[4]
            board_id, card_id, checkitem_id, source = (
                (rec[5], rec[6], rec[7], rec[8]) if len(rec) >= 9 else ("", "", None, "card"))
            block = [
                {"type": "text", "text": headline, "weight": "bold", "color": color, "size": "md", "wrap": True},
                {"type": "text", "text": sub, "size": "xs", "color": "#999999", "wrap": True, "margin": "xs"},
            ]
            if raw:
                block.append({"type": "text", "text": raw, "size": "sm", "color": "#333333", "wrap": True, "margin": "sm"})
            if card_id:
                block.append(_status_buttons(board_id, card_id, checkitem_id, source))
            box = {"type": "box", "layout": "vertical", "contents": block}
            if i > 0:
                body.append({"type": "separator", "margin": "lg"})
                box["margin"] = "lg"
            body.append(box)
        bubbles.append({
            "type": "bubble", "size": "mega",
            "header": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": f"意念情境・{mode_label}專案提醒", "size": "xs", "color": "#AAAAAA"},
                {"type": "text", "text": board, "weight": "bold", "size": "md", "wrap": True, "color": "#1A1A1A", "margin": "sm"},
            ]},
            "body": {"type": "box", "layout": "vertical", "contents": body},
        })

    def _summary_bubble(now_str, title, body, title_color="#1A1A1A"):
        # 與專案提醒同款 header：灰色副標 + 粗體標題
        return {
            "type": "bubble", "size": "mega",
            "header": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": f"意念情境・每日工程摘要 {now_str}", "size": "xs", "color": "#AAAAAA"},
                {"type": "text", "text": title, "weight": "bold", "size": "md", "wrap": True, "color": title_color, "margin": "sm"},
            ]},
            "body": {"type": "box", "layout": "vertical", "contents": body},
        }

    def _status_color(lst):
        if "已完成" in lst: return "#388E3C"   # 綠
        if "執行中" in lst: return "#EF6C00"   # 橙
        if "未執行" in lst: return "#1976D2"   # 藍
        return "#666666"

    for rec in summaries:
        _, now_str, sections, warnings = rec
        # 空摘要不佔位（無內容主管於拉取時由上層回「今日無提醒」）
        # 每看板一張 bubble：依狀態欄分組（彩色欄頭 + 分隔線），卡片名一次、工項列其下
        for board, columns in sections:
            body = []
            for ci, (lst, cards) in enumerate(columns):
                if ci > 0:
                    body.append({"type": "separator", "margin": "lg"})
                body.append({"type": "text", "text": lst, "weight": "bold", "size": "sm",
                             "color": _status_color(lst), "wrap": True, "margin": ("none" if ci == 0 else "lg")})
                for card, labels in cards:
                    block = [{"type": "text", "text": card, "size": "sm", "weight": "bold",
                              "color": "#1A1A1A", "wrap": True, "margin": "md"}]
                    for lb, overdue in labels:
                        if lb == card and not overdue:
                            continue  # label 等於卡片名（tag 未填 label 預設值）且未逾期 → 不重列
                        if lb == card:
                            txt, col = "⚠️ 逾期", "#D32F2F"
                        elif overdue:
                            txt, col = f"⚠️ {lb}（逾期）", "#D32F2F"
                        else:
                            txt, col = lb, "#666666"
                        block.append({"type": "text", "text": f"・{txt}", "size": "xs",
                                      "color": col, "wrap": True, "margin": "xs"})
                    body.append({"type": "box", "layout": "vertical", "contents": block})
            bubbles.append(_summary_bubble(now_str, board, body))
        # 警告各自一張 bubble，標題即內容主旨（alias / 未歸欄）
        for title, wlines in warnings:
            color = "#D32F2F" if title.startswith("⚠️") else "#388E3C"
            body = [{"type": "text", "text": ln, "size": "sm", "color": "#333333", "wrap": True,
                     "margin": ("none" if i == 0 else "sm")} for i, ln in enumerate(wlines)]
            bubbles.append(_summary_bubble(now_str, title, body, title_color=color))

    bubbles = bubbles[:12]   # LINE carousel 上限 12 張
    if len(bubbles) == 1:
        return bubbles[0]
    return {"type": "carousel", "contents": bubbles}


def test_send():
    contacts = load_contacts()
    now_str = datetime.now(TAIPEI).strftime("%Y/%m/%d %H:%M")
    msg = f"✅ LINE 通知系統測試成功！\n時間：{now_str}\n\n意念情境自動通知系統已就緒。"

    for name in ("larry", "larryoffice"):
        uid = ((_resolve_tag_recipients([name]) or [None])[0]) or contacts.get(name)
        if not uid:
            print(f"找不到 {name} 的 LINE ID，略過")
            continue
        status, resp = send_line(uid, msg)
        print(f"→ {name} ({uid[:8]}...)  狀態:{status}")


DAILY_LABEL = "今日"


def build_daily_messages_for_user(user_id, role=None):
    """組裝某使用者的每日內容（on-demand 拉取共用）。回傳 LINE message 物件陣列，
    無內容回 []。內容定義與每日批次一致：跑 run_checks() 後過濾出該 uid 的項目；
    主管(internal) 因 run_checks 已附其摘要與確認卡，過濾後即包含。"""
    notifications = run_checks()
    items = [(board_name, rec) for uid, board_name, rec in notifications if uid == user_id]
    if not items:
        return []
    contents = build_flex(items, DAILY_LABEL)
    alt = f"意念情境 {DAILY_LABEL}提醒（{len(items)} 則）"
    return [{"type": "flex", "altText": alt[:400], "contents": contents}]


def run_daily_push():
    """單一每日批次的主動 push：僅送 role=vendor 的收件人；空內容不送。
    主管/客戶不 push，改由 Rich Menu on-demand 拉取（免費 Reply API）取得。"""
    notifications = run_checks()
    grouped = {}
    for uid, board_name, rec in notifications:
        grouped.setdefault(uid, []).append((board_name, rec))
    roles = _roles_by_lineid(list(grouped.keys()))
    sent = 0
    for uid, items in grouped.items():
        if roles.get(uid) != "vendor":   # 僅廠商收主動 push
            continue
        if not items:                    # skip-empty
            continue
        contents = build_flex(items, DAILY_LABEL)
        alt = f"意念情境 {DAILY_LABEL}提醒（{len(items)} 則）"
        status, resp = send_flex(uid, contents, alt)
        sent += 1
        print(f"→ {uid[:8]}... 狀態:{status}")
    print(f"[daily] pushed to {sent} vendor(s)")


def main():
    import sys
    args = sys.argv[1:]
    if args and args[0] == "test":
        test_send()
    elif args and args[0] in ("noon", "evening"):
        # 已合併為單一每日批次；保留參數相容但不送，避免舊 CronJob 殘留造成重複推播。
        print(f"[{args[0]}] deprecated: consolidated into single daily run; nothing sent.")
    elif not args or args[0] in ("daily", "morning"):
        # 'morning' 視為 'daily' 別名，方便沿用既有排程命名。
        run_daily_push()
    else:
        print("用法：python3 trello_line_notifier.py [daily|test]")


if __name__ == "__main__":
    main()
