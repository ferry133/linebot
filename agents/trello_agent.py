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
from shared.db import db_exec
from trello_line_notifier import (
    TAIPEI,
    WORKSPACE_ID,
    get_boards_batch,
    parse_tag,
    days_diff,
)

AGENT_ID = "trello_agent"
REQUEST_TOPIC = "agents/trello/requests"
INVALIDATE_TOPIC = "agents/trello/invalidate"
TRELLO_CACHE_TTL = 60


class TrelloAgent:
    def __init__(self, broker: MQTTBroker):
        self.broker = broker
        self.memory = AgentMemory(AGENT_ID)
        self._cache: dict = {"items": None, "ts": 0.0}

    def _load_boards_from_db(self) -> list[dict]:
        """Read board id/name from trello_boards table. Returns [] if DB unavailable."""
        def _fetch(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT board_id, board_name FROM trello_boards WHERE workspace_id = %s",
                    (WORKSPACE_ID,),
                )
                return [{"id": row[0], "name": row[1]} for row in cur.fetchall()]
        result = db_exec(_fetch)
        return result or []

    def start(self):
        self.broker.subscribe(REQUEST_TOPIC, self._on_request)
        self.broker.subscribe(INVALIDATE_TOPIC, self._on_invalidate)
        log.info(f"[{AGENT_ID}] Listening on {REQUEST_TOPIC}")

    def _on_invalidate(self, payload: dict):
        """A write (by customer-service) happened — drop the scan cache so the next
        query reflects the new Trello state instead of stale cached items."""
        self._cache["items"] = None
        self._cache["ts"] = 0.0
        log.info(f"[{AGENT_ID}] scan cache invalidated")

    def _on_request(self, payload: dict):
        request_id = payload.get("request_id", "")
        reply_to = payload.get("reply_to", "")
        query_type = payload.get("query_type", "all")
        keyword = payload.get("keyword", "")

        if not reply_to:
            log.info(f"[{AGENT_ID}] Missing reply_to in request {request_id}")
            return

        allowed_board_ids = payload.get("allowed_board_ids", payload.get("allowed_boards"))  # None=all, []=blocked, [str]=filter by board_id
        project_map = payload.get("project_map") or {}  # {board_id: project_name}
        owner_alias = payload.get("owner_alias")  # None=no owner filter; str (incl "")=only items tagged to this alias (廠商)
        log.info(f"[{AGENT_ID}] Request {request_id[:8]}: type={query_type} keyword={keyword} allowed_ids={allowed_board_ids} owner={owner_alias} projects={len(project_map)}")
        result = self._query(query_type, keyword, allowed_board_ids, project_map, owner_alias)
        self.broker.publish(reply_to, {
            "request_id": request_id,
            "result": result,
        })

    def _get_target_boards(self) -> list[dict]:
        boards = self._load_boards_from_db()
        if boards:
            filtered = [b for b in boards if "母版" not in b["name"]]
            log.info(f"[{AGENT_ID}] Loaded {len(filtered)} boards from DB")
            return filtered
        # DB empty (sync job not yet run) — fall back to live API
        log.info(f"[{AGENT_ID}] DB has no boards, falling back to Trello API")
        from trello_line_notifier import get_boards
        return [b for b in get_boards() if "母版" not in b["name"]]

    def _scan_all_items(self) -> list[dict]:
        now = time.monotonic()
        if (self._cache["items"] is not None
                and now - self._cache["ts"] < TRELLO_CACHE_TTL):
            return list(self._cache["items"])

        target = self._get_target_boards()
        name_map = {b["id"]: b["name"] for b in target}
        boards_data = get_boards_batch([b["id"] for b in target])
        items = []
        for board in boards_data:
            board_name = name_map.get(board["id"], board["name"])
            for card in board["cards"]:
                list_name = board["lists"].get(card.get("idList", ""), "")
                if card.get("desc"):
                    parsed = parse_tag(card["desc"].split("\n")[0])
                    if parsed:
                        names, start, end, end_time, label = parsed
                        items.append({
                            "board": board_name, "board_id": board["id"], "list": list_name,
                            "card": card["name"], "label": label or card["name"],
                            "names": names, "start": str(start), "end": str(end),
                            "source": "card_desc",
                        })
                for cl in card.get("checklists", []):
                    for it in cl.get("checkItems", []):
                        parsed = parse_tag(it["name"])
                        if not parsed:
                            continue
                        names, start, end, end_time, label = parsed
                        items.append({
                            "board": board_name, "board_id": board["id"], "list": list_name,
                            "card": card["name"], "label": label,
                            "names": names, "start": str(start), "end": str(end),
                            "state": it["state"], "source": "checklist",
                        })

        self._cache["items"] = items
        self._cache["ts"] = time.monotonic()
        log.info(f"[{AGENT_ID}] Scanned {len(items)} items from {len(boards_data)} boards")
        return items

    def _query(self, query_type: str, keyword: str = "",
               allowed_board_ids: list[str] | None = None,
               project_map: dict | None = None,
               owner_alias: str | None = None) -> str:
        project_map = project_map or {}
        try:
            items = self._scan_all_items()
        except Exception as e:
            log.info(f"[{AGENT_ID}] Trello error: {e}")
            return f"查詢 Trello 失敗：{e}"

        # Per-user authorization filter (None = no restriction); exact board_id match
        if allowed_board_ids is not None:
            allowed_set = set(allowed_board_ids)
            items = [i for i in items if i.get("board_id") in allowed_set]

        # 廠商 owner 層過濾：只留 names 含該 alias 的工項（None=不過濾；""=無可對應→空）
        if owner_alias is not None:
            items = [i for i in items if owner_alias in [n.lower() for n in i.get("names", [])]]

        # Attach project_name (falls back to Trello board name if no mapping)
        for i in items:
            i["project_name"] = project_map.get(i.get("board_id"), i["board"])

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
                if kw in i["project_name"].lower() or kw in i["card"].lower()
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
                f"・{i['project_name']} / {i['list']} / {i['card']}\n"
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
