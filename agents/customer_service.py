#!/usr/bin/env python3
"""
Customer Service Agent — 五步循環

Perceive → Recall → Reason+Act → Reflect

訂閱 MQTT agents/customer_service/inbox
→ Claude agentic loop（query_trello / escalate_to_manager）
→ 發布回覆至 gateway/outbox
→ reflect() 寫入 episodes + knowledge
"""

import os
import time
from datetime import datetime, date

import anthropic

from agents.base.memory import AgentMemory
from shared.broker import MQTTBroker
from trello_line_notifier import (
    TAIPEI,
    get_boards,
    get_lists,
    get_cards,
    parse_tag,
    days_diff,
    send_line,
)

AGENT_ID = "customer_service"
INBOX_TOPIC = f"agents/{AGENT_ID}/inbox"
OUTBOX_TOPIC = "gateway/outbox"

MODEL = "claude-haiku-4-5-20251001"
MAX_TOOL_TURNS = 5
TRELLO_CACHE_TTL = 60

LINE_NOTIFY_GROUP_ID = os.environ.get("LINE_NOTIFY_GROUP_ID", "")

SYSTEM_PROMPT = """你是「意念情境室內裝修」的 LINE 客服助理。

【公司簡介】
意念情境室內裝修提供住宅與商業空間的設計、施工與監工服務，服務範圍包含全室裝修、局部改造、木作工程、水電配管、地板磁磚等。

【你能回答的問題】
- 公司服務項目、施工流程、報價方式
- 工程進度、各工班預計到場時間、工項排程
- 費用說明、付款階段、付款狀態（從工程看板查詢）
- 材料選樣、工期估算等一般諮詢

【回應原則】
- 語氣親切、專業，使用繁體中文
- 回答要具體有幫助，若資訊不足可主動說明需要哪些資訊
- 查詢工程進度時，先用 query_trello 工具取得即時資料再回答
- 遇到無法確定、需要人工判斷、或涉及合約細節的問題，使用 escalate_to_manager 工具轉交專人

【不要做的事】
- 不要編造工程進度或日期
- 不要承諾具體報價金額（引導客戶預約現場勘查）
- 不要提供個人資料或其他客戶資訊
"""

TOOLS = [
    {
        "name": "query_trello",
        "description": "查詢 Trello 工程看板的即時資料，包含所有工項進度、排程、逾期狀況等。查詢客戶工程進度時請使用此工具。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": ["all", "overdue", "upcoming", "specific"],
                    "description": "all=全部工項概況, overdue=逾期工項, upcoming=7天內到期, specific=關鍵字搜尋",
                },
                "keyword": {
                    "type": "string",
                    "description": "query_type=specific 時的搜尋關鍵字（客戶姓名、工項名稱、看板名稱）",
                },
            },
            "required": ["query_type"],
        },
    },
    {
        "name": "escalate_to_manager",
        "description": "當問題超出客服範圍、需要人工判斷、或無法確定答案時，通知管理人員處理。",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "customer_question": {"type": "string"},
            },
            "required": ["reason", "customer_question"],
        },
    },
]


class ActionResult:
    def __init__(self, final_text: str = "", escalated: bool = False,
                 error: str = "", tools_used: list = None):
        self.final_text = final_text
        self.escalated = escalated
        self.error = error
        self.tools_used = tools_used or []


class CustomerServiceAgent:
    def __init__(self, broker: MQTTBroker):
        self.broker = broker
        self.memory = AgentMemory(AGENT_ID)
        self.client = anthropic.Anthropic()
        self._trello_cache: dict = {"items": None, "ts": 0.0}

    def start(self):
        self.broker.subscribe(INBOX_TOPIC, self._on_message)
        print(f"[{AGENT_ID}] Listening on {INBOX_TOPIC}")

    # ── MQTT handler ──────────────────────────────────────────────────────────

    def _on_message(self, payload: dict):
        user_id = payload.get("user_id", "unknown")
        text = payload.get("text", "")
        if not text:
            return
        print(f"[{AGENT_ID}] Received from {user_id[:8]}: {text[:60]}")
        try:
            reply = self._run(user_id, text)
            self.broker.publish(OUTBOX_TOPIC, {
                "user_id": user_id,
                "content": reply,
            })
        except Exception as e:
            print(f"[{AGENT_ID}] Error: {e}")
            self.broker.publish(OUTBOX_TOPIC, {
                "user_id": user_id,
                "content": "抱歉，系統暫時異常，請稍後再試。",
            })

    # ── 五步循環 ──────────────────────────────────────────────────────────────

    def _run(self, user_id: str, user_message: str) -> str:
        # 1. Perceive
        situation = self._perceive(user_id, user_message)

        # 2. Recall
        memory_context = self._recall(situation)

        # 3. Reason + Act
        result = self._reason_and_act(user_id, user_message, memory_context)

        # 4. Reflect
        self._reflect(situation, result)

        # 5. Reply
        if result.escalated and not result.final_text:
            return "您好，您的問題已轉交給專人處理，我們會盡快與您聯繫，感謝您的耐心等候！"
        return result.final_text[:5000] if result.final_text else "抱歉，目前無法處理您的問題，已通知專人跟進。"

    def _perceive(self, user_id: str, text: str) -> str:
        return f"用戶訊息：{text}"

    def _recall(self, situation: str) -> str:
        knowledge = self.memory.get_knowledge(situation)
        episodes = self.memory.recall_episodes(situation)
        parts = []
        if knowledge:
            parts.append("【已知規律】\n" + "\n".join(
                f"・{k['fact']}（信心：{k['confidence']:.0%}）"
                for k in knowledge
            ))
        if episodes:
            parts.append("【過去經驗】\n" + "\n".join(
                f"・{e['situation'][:50]}... → {'✓ 成功' if e['quality'] > 0.7 else '✗ 待改進'}"
                for e in episodes
            ))
        if parts:
            context = "\n\n".join(parts)
            print(f"[{AGENT_ID}] Recalled: {len(knowledge)} knowledge, {len(episodes)} episodes")
            return context
        return ""

    def _reason_and_act(self, user_id: str, user_message: str,
                        memory_context: str) -> ActionResult:
        system = SYSTEM_PROMPT
        if memory_context:
            system += f"\n\n{memory_context}"

        history = self.memory.get_working(user_id)
        new_messages = [{"role": "user", "content": user_message}]
        escalated = False
        final_text = ""
        tools_used = []

        for _ in range(MAX_TOOL_TURNS):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=system,
                messages=history + new_messages,
                tools=TOOLS,
            )
            new_messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text = block.text
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    tools_used.append(block.name)
                    if block.name == "query_trello":
                        result = self._query_trello(
                            block.input.get("query_type", "all"),
                            block.input.get("keyword", ""),
                        )
                    elif block.name == "escalate_to_manager":
                        self._escalate(
                            block.input.get("reason", ""),
                            block.input.get("customer_question", user_message),
                            user_id,
                        )
                        escalated = True
                        result = "已通知管理人員。"
                    else:
                        result = "未知工具。"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
                new_messages.append({"role": "user", "content": tool_results})
            else:
                break

        self.memory.append_working(user_id, new_messages)
        return ActionResult(
            final_text=final_text,
            escalated=escalated,
            tools_used=tools_used,
        )

    def _reflect(self, situation: str, result: ActionResult):
        quality = self._evaluate(result)
        action_summary = f"工具：{result.tools_used}" if result.tools_used else "直接回答"

        self.memory.store_episode(
            situation=situation,
            action=action_summary,
            result=result.final_text[:200] if result.final_text else f"escalated={result.escalated}",
            quality=quality,
        )
        print(f"[{AGENT_ID}] Reflected: quality={quality:.1f}, tools={result.tools_used}")

        # 提煉語意知識
        if quality >= 0.8 and result.tools_used:
            insight = f"問題「{situation[:40]}」使用 {result.tools_used} 成功解答"
            self.memory.store_knowledge(insight, confidence=quality)
        elif result.escalated:
            insight = f"問題「{situation[:40]}」需要人工處理"
            self.memory.store_knowledge(insight, confidence=0.7)
        elif result.error:
            insight = f"問題「{situation[:40]}」處理失敗：{result.error[:50]}"
            self.memory.store_knowledge(f"避免：{insight}", confidence=0.8)

    def _evaluate(self, result: ActionResult) -> float:
        if result.error:
            return 0.1
        if result.escalated:
            return 0.5
        if len(result.final_text) > 100:
            return 0.8
        if len(result.final_text) > 20:
            return 0.6
        return 0.3

    # ── Trello ────────────────────────────────────────────────────────────────

    def _scan_all_items(self) -> list[dict]:
        now = time.monotonic()
        if (self._trello_cache["items"] is not None
                and now - self._trello_cache["ts"] < TRELLO_CACHE_TTL):
            return list(self._trello_cache["items"])

        boards = get_boards()
        print(f"[{AGENT_ID}] Trello boards: {[b['name'] for b in boards]}")
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

        self._trello_cache["items"] = items
        self._trello_cache["ts"] = time.monotonic()
        return items

    def _query_trello(self, query_type: str, keyword: str = "") -> str:
        try:
            items = self._scan_all_items()
            print(f"[{AGENT_ID}] Trello scanned: {len(items)} items")
        except Exception as e:
            print(f"[{AGENT_ID}] Trello error: {e}")
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

    # ── Escalation ────────────────────────────────────────────────────────────

    def _escalate(self, reason: str, customer_question: str, source_user_id: str):
        now = datetime.now(TAIPEI).strftime("%Y/%m/%d %H:%M")
        msg = (
            f"⚠️ LINE 客服轉交通知\n"
            f"時間：{now}\n"
            f"客戶問題：{customer_question}\n"
            f"原因：{reason}\n"
            f"客戶 ID：{source_user_id[:8]}..."
        )
        if LINE_NOTIFY_GROUP_ID:
            send_line(LINE_NOTIFY_GROUP_ID, msg)
        else:
            try:
                from trello_line_notifier import load_contacts
                contacts = load_contacts()
                for name in ("sa", "larry"):
                    uid = contacts.get(name)
                    if uid:
                        send_line(uid, msg)
            except Exception:
                pass


if __name__ == "__main__":
    broker = MQTTBroker(client_id=AGENT_ID)
    agent = CustomerServiceAgent(broker)
    broker.connect()
    agent.start()
    print(f"[{AGENT_ID}] Agent running...")
    broker.loop_forever()
