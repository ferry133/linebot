#!/usr/bin/env python3
"""
Trello Agent — 獨立 process

訂閱 agents/trello/requests
→ 查詢 Trello API
→ 發布結果至 payload 指定的 reply_to topic
"""

import logging
import time
from datetime import datetime, date

from shared.log import setup as _setup_log
_setup_log()
log = logging.getLogger(__name__)

from agents.base.memory import AgentMemory
from shared.broker import MQTTBroker
from trello_line_notifier import (
    TAIPEI,
    get_boards,
    get_lists,
    get_cards,
    parse_tag,
    days_diff,
)

AGENT_ID = "trello_agent"
REQUEST_TOPIC = "agents/trello/requests"
TRELLO_CACHE_TTL = 60


class TrelloAgent:
    def __init__(self, broker: MQTTBroker):
        self.broker = broker
        self.memory = AgentMemory(AGENT_ID)
        self._cache: dict = {"items": None, "ts": 0.0}

    def start(self):
        self.broker.subscribe(REQUEST_TOPIC, self._on_request)
        log.info(f"[{AGENT_ID}] Listening on {REQUEST_TOPIC}")

    def _on_request(self, payload: dict):
        request_id = payload.get("request_id", "")
        reply_to = payload.get("reply_to", "")
        query_type = payload.get("query_type", "all")
        keyword = payload.get("keyword", "")

        if not reply_to:
            log.info(f"[{AGENT_ID}] Missing reply_to in request {request_id}")
            return

        log.info(f"[{AGENT_ID}] Request {request_id[:8]}: type={query_type} keyword={keyword}")
        result = self._query(query_type, keyword)
        self.broker.publish(reply_to, {
            "request_id": request_id,
            "result": result,
        })

    def _scan_all_items(self) -> list[dict]:
        now = time.monotonic()
        if (self._cache["items"] is not None
                and now - self._cache["ts"] < TRELLO_CACHE_TTL):
            return list(self._cache["items"])

        boards = get_boards()
        items = []
        for board in boards:
            if "母版" in board["name"]:
                continue
            list_map = get_lists(board["id"])
            cards = get_cards(board["id"])
            for card in cards:
                list_name = list_map.get(card.get("idList", ""), "")
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

        self._cache["items"] = items
        self._cache["ts"] = time.monotonic()
        log.info(f"[{AGENT_ID}] Scanned {len(items)} items from {len(boards)} boards")
        return items

    def _query(self, query_type: str, keyword: str = "") -> str:
        try:
            items = self._scan_all_items()
        except Exception as e:
            log.info(f"[{AGENT_ID}] Trello error: {e}")
            return f"查詢 Trello 失敗：{e}"

        if not items:
            return "目前 Trello 無任何有標記的工項。"

        if query_type == "overdue":
            filtered = [
                i for i in items
                if i["end"] != "None" and i.get("state") != "complete"
                and days_diff(date.fromisoformat(i["end"])) < 0
            ]
            label = "逾期工項"
        elif query_type == "upcoming":
            filtered = [
                i for i in items
                if i["end"] != "None" and i.get("state") != "complete"
                and 0 <= days_diff(date.fromisoformat(i["end"])) <= 7
            ]
            label = "7 天內到期工項"
        elif query_type == "specific" and keyword:
            kw = keyword.lower()
            filtered = [
                i for i in items
                if kw in i["board"].lower() or kw in i["card"].lower()
                or kw in i["label"].lower() or any(kw in n for n in i["names"])
            ]
            label = f"關鍵字「{keyword}」相關工項"
        else:
            filtered = items
            label = "所有工項"

        if not filtered:
            return f"查無{label}。"

        now = datetime.now(TAIPEI).strftime("%Y/%m/%d %H:%M")
        lines = [f"📋 {label}（查詢時間：{now}，共 {len(filtered)} 項）\n"]
        for i in filtered:
            state_str = " ✓" if i.get("state") == "complete" else (
                " ⬜" if i.get("state") == "incomplete" else "")
            end_str = f"，到期：{i['end']}" if i["end"] != "None" else ""
            lines.append(
                f"・{i['board']} / {i['list']} / {i['card']}\n"
                f"  {i['label']}{state_str}{end_str}"
            )
        return "\n".join(lines)


if __name__ == "__main__":
    broker = MQTTBroker(client_id=AGENT_ID)
    agent = TrelloAgent(broker)
    broker.connect()
    agent.start()
    log.info(f"[{AGENT_ID}] Agent running...")
    broker.loop_forever()
