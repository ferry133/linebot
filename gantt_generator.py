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
import re
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

ITEM_RE = re.compile(
    r"\[@((?:@?\([^)]+\))+),\s*(\d{8})?-?(\d{8})?(?::(\d{4}))?\](.+)"
)
NAME_RE = re.compile(r"\(([^)]+)\)")

# 甘特圖時間範圍：26 週，從 2026-04-26（週日）起
GANTT_START = date(2026, 4, 26)
GANTT_WEEKS = 26
WEEKS = [GANTT_START + timedelta(weeks=i) for i in range(GANTT_WEEKS)]


def parse_tag(text):
    m = ITEM_RE.match(text.strip())
    if not m:
        return None
    names = NAME_RE.findall(m.group(1))
    start = datetime.strptime(m.group(2), "%Y%m%d").date() if m.group(2) else None
    end = datetime.strptime(m.group(3), "%Y%m%d").date() if m.group(3) else None
    label = m.group(5).strip()
    return names, start, end, label


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
        "fields": "name,desc,idList,dueComplete",
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


def collect_items():
    boards = get_boards()
    rows = []

    for board in boards:
        board_name = board["name"]
        # 跳過範本看板（名稱含「母版」）
        if "母版" in board_name:
            continue
        list_map = get_lists(board["id"])
        cards = get_cards(board["id"])

        for card in cards:
            list_name = list_map.get(card.get("idList", ""), "")

            # Card description 第一行
            if card.get("desc"):
                first_line = card["desc"].split("\n")[0]
                parsed = parse_tag(first_line)
                if parsed and not any("??" in n for n in parsed[0]):  # 略過未定負責人(??)
                    names, start, end, label = parsed
                    rows.append({
                        "board": board_name,
                        "list": list_name,
                        "card": card["name"],
                        "label": label,
                        "names": "、".join(names),
                        "start": start,
                        "end": end,
                        # card 層級工項完成 = 卡片 dueComplete（與通知邏輯一致），
                        # 否則 dueComplete 的完成卡會被誤判逾期。
                        "state": "complete" if card.get("dueComplete") else "incomplete",
                    })

            # Checklist 項目
            for checklist in card.get("checklists", []):
                for item in checklist.get("checkItems", []):
                    parsed = parse_tag(item["name"])
                    if not parsed:
                        continue
                    if any("??" in n for n in parsed[0]):  # 略過未定負責人(??)
                        continue
                    names, start, end, label = parsed
                    rows.append({
                        "board": board_name,
                        "list": list_name,
                        "card": card["name"],
                        "label": label,
                        "names": "、".join(names),
                        "start": start,
                        "end": end,
                        "state": item["state"],
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
