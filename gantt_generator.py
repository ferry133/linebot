#!/usr/bin/env python3
"""
讀取 Trello 工項資料，產生甘特圖 CSV。

使用方式：
  python3 gantt_generator.py           → 產生 gantt.csv
  bash run.sh gantt                    → 含 SOPS 解密後執行

產生的 gantt.csv 可直接匯入 Google Sheets，或由 Claude 透過 Google Drive MCP 上傳。
"""

import os
import csv
import requests
from datetime import date, datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
TRELLO_KEY = os.environ.get("TRELLO_API_KEY", "")
TRELLO_TOKEN = os.environ.get("TRELLO_TOKEN", "")
WORKSPACE_ID = "jiahomedesign1"

# 工項定義與 LINE 通知共用（spec work-item-tag）：文字標記＋Trello 原生日期
from trello_line_notifier import work_item_of_card, work_item_of_checkitem, COMPANY_LABEL

# 甘特圖時間範圍：26 週，從 2026-04-26（週日）起
GANTT_START = date(2026, 4, 26)
GANTT_WEEKS = 26
WEEKS = [GANTT_START + timedelta(weeks=i) for i in range(GANTT_WEEKS)]


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
        "checkItem_fields": "name,state,due,idMember",
        "fields": "name,desc,idList,dueComplete,start,due",
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def week_overlaps(week_start, start, end):
    """判斷該週是否與工項日期範圍重疊"""
    week_end = week_start + timedelta(days=6)
    if start and end:
        return start <= week_end and end >= week_start
    elif start:
        return week_end >= start
    elif end:
        return week_start <= end
    return False


def _valid_aliases():
    """已註冊 line_users.alias_name 的小寫 set（與 LINE「查無對應」同一來源），
    無 DB 時回 None（不過濾）。一次查詢，由 collect_items 快取重用。"""
    try:
        from shared.db import db_exec
    except Exception:
        return None
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT alias_name FROM line_users "
                        "WHERE alias_name IS NOT NULL AND alias_name <> ''")
            return {r[0].lower() for r in cur.fetchall()}
    try:
        return db_exec(_q)
    except Exception:
        return None


def collect_items():
    boards = get_boards()
    rows = []
    valid = _valid_aliases()   # 一次查詢，整批重用；None=無 DB → 不過濾
    def _unmatched(names):     # 負責人有任一不在用戶管理 → 該工項不列入
        return valid is not None and any(n.lower() not in valid for n in names)

    for board in boards:
        board_name = board["name"]
        # 跳過範本看板（名稱含「母版」）
        if "母版" in board_name:
            continue
        list_map = get_lists(board["id"])
        cards = get_cards(board["id"])

        for card in cards:
            list_name = list_map.get(card.get("idList", ""), "")

            # 卡片層級（原生 `@`＋Trello 日期，或描述第一行）＋待辦項；完成狀態由工項定義給出
            wis = [work_item_of_card(card)] + [work_item_of_checkitem(item, card)
                                               for checklist in card.get("checklists", [])
                                               for item in checklist.get("checkItems", [])]
            for wi in wis:
                if not wi or _unmatched(wi["names"]):
                    continue
                rows.append({
                    "board": board_name,
                    "list": list_name,
                    "card": card["name"],
                    "label": wi["label"],
                    "names": COMPANY_LABEL if wi["company"] else "、".join(wi["names"]),
                    "start": wi["start"],
                    "end": wi["end"],
                    "state": "complete" if wi["complete"] else "incomplete",
                })

    return rows


def generate_csv(output_path="gantt.csv"):
    rows = collect_items()

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        # Row 1: 實際日期值（供 conditional formatting 使用）
        writer.writerow(
            ["", "", "", "", "", "", "", ""]
            + [w.strftime("%Y/%m/%d") for w in WEEKS]
        )

        # Row 2: 欄位標題
        writer.writerow(
            ["案件", "清單", "卡片", "工項名稱", "負責人", "開始日", "結束日", "狀態"]
            + [w.strftime("%m/%d") for w in WEEKS]
        )

        # 資料列
        for row in rows:
            if row["state"] == "complete":
                status = "✓ 完成"
            elif row["state"] == "incomplete":
                status = "進行中"
            else:
                status = ""

            gantt = [
                "■" if week_overlaps(w, row["start"], row["end"]) else ""
                for w in WEEKS
            ]

            writer.writerow([
                row["board"],
                row["list"],
                row["card"],
                row["label"],
                row["names"],
                row["start"].strftime("%Y/%m/%d") if row["start"] else "",
                row["end"].strftime("%Y/%m/%d") if row["end"] else "",
                status,
            ] + gantt)

    print(f"✅ 甘特圖已產生：{output_path}（{len(rows)} 個工項）")
    return output_path


if __name__ == "__main__":
    generate_csv()
