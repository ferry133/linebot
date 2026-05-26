#!/usr/bin/env python3
"""
Customer Service Agent — 五步循環

Perceive → Recall → Reason+Act → Reflect

訂閱 MQTT agents/customer_service/inbox
→ Claude agentic loop（query_trello / escalate_to_manager）
→ 發布回覆至 gateway/outbox
→ reflect() 寫入 episodes + knowledge

Trello 查詢委託給 TrelloAgent（MQTT request/reply）
"""

import logging
import os
import re
import threading
import uuid
from datetime import datetime

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)

from shared.log import setup as _setup_log
_setup_log()
log = logging.getLogger(__name__)

import anthropic
import json
import yaml

from agents.base.memory import AgentMemory
from shared.broker import MQTTBroker
from shared.db import db_exec
from trello_line_notifier import TAIPEI, send_line

AGENT_ID = "customer_service"
INBOX_TOPIC = f"agents/{AGENT_ID}/inbox"
OUTBOX_TOPIC = "gateway/outbox"
TRELLO_REQUEST_TOPIC = "agents/trello/requests"
TRELLO_REPLY_PREFIX = "agents/trello/responses"
TRELLO_TIMEOUT = 30  # 秒

MODEL = "claude-haiku-4-5-20251001"
MAX_TOOL_TURNS = 5
KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge")


def _load_knowledge_base() -> str:
    try:
        if not os.path.isdir(KNOWLEDGE_DIR):
            return ""
        parts = []
        for fname in sorted(os.listdir(KNOWLEDGE_DIR)):
            if fname.endswith(".md"):
                try:
                    with open(os.path.join(KNOWLEDGE_DIR, fname), encoding="utf-8") as f:
                        parts.append(_FRONTMATTER_RE.sub("", f.read(), count=1))
                except OSError:
                    pass
        return "\n\n---\n\n".join(parts)
    except OSError as e:
        log.warning(f"Cannot load knowledge base: {e}")
        return ""


def _load_project_photos() -> dict:
    path = os.path.join(KNOWLEDGE_DIR, "project_photos.yaml")
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except OSError:
        return {}


def _all_active_projects() -> dict:
    """Returns {board_id: project_name} for all active projects with a Trello board."""
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT trello_board_id, name FROM projects "
                "WHERE trello_board_id IS NOT NULL AND status = 'active'"
            )
            return {r[0]: r[1] for r in cur.fetchall()}
    try:
        return db_exec(_q) or {}
    except Exception:
        return {}


def _get_user_role_and_projects(user_id: str) -> tuple:
    """Return (role, projects) where projects is [{'name': str, 'board_id': str}] for active projects with a Trello board."""
    def _query(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM line_users WHERE line_id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                return None, []
            role = row[0]
            cur.execute(
                "SELECT p.name, p.trello_board_id FROM line_user_projects lup "
                "JOIN projects p ON p.project_id = lup.project_id "
                "WHERE lup.line_id = %s AND p.trello_board_id IS NOT NULL AND p.status = 'active'",
                (user_id,),
            )
            projects = [{"name": r[0], "board_id": r[1]} for r in cur.fetchall()]
            return role, projects

    try:
        result = db_exec(_query)
    except Exception:
        result = None

    if result is None or result[0] is None:
        return "visitor", []
    return result[0], result[1]


_KNOWLEDGE_BASE = _load_knowledge_base()

LINE_NOTIFY_GROUP_ID = os.environ.get("LINE_NOTIFY_GROUP_ID", "")

_BASE_SYSTEM_PROMPT = """你是「意念情境室內裝修」的 LINE 客服助理。

【公司簡介】
意念情境室內裝修提供住宅與商業空間的設計、施工與監工服務，服務範圍包含全室裝修、局部改造、木作工程、水電配管、地板磁磚等。

【你能回答的問題】
- 公司服務項目、施工流程、報價方式
- 工程進度、各工班預計到場時間、工項排程
- 費用說明、付款階段、付款狀態（從工程看板查詢）
- 材料選樣、工期估算等一般諮詢
- 客戶詢問工地照片時，使用 get_project_photos 工具取得相簿連結

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

SYSTEM_PROMPT = _BASE_SYSTEM_PROMPT + (
    f"\n\n【室內裝修知識庫】\n以下是室內裝修相關知識，供你回答客戶諮詢時參考：\n\n{_KNOWLEDGE_BASE}"
    if _KNOWLEDGE_BASE else ""
)

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
        "name": "get_project_photos",
        "description": "取得客戶工地的施工照片相簿連結。客戶詢問工地照片、施工現況照片時使用此工具。",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "工程名稱或客戶姓名關鍵字，用於比對對應的相簿",
                },
            },
            "required": ["project_name"],
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
        self._pending: dict[str, tuple[threading.Event, list]] = {}

    def start(self):
        self.broker.subscribe(INBOX_TOPIC, self._on_message)
        self.broker.subscribe(f"{TRELLO_REPLY_PREFIX}/#", self._on_trello_reply)
        log.info(f"[{AGENT_ID}] Listening on {INBOX_TOPIC}")

    # ── MQTT handler ──────────────────────────────────────────────────────────

    def _on_message(self, payload: dict):
        user_id = payload.get("user_id", "unknown")
        text = payload.get("text", "")
        if not text:
            return
        log.info(f"[{AGENT_ID}] Received from {user_id[:8]}: {text[:60]}")
        # 背景執行，避免阻塞 MQTT loop（event.wait 需要 loop 持續運作才能收到 Trello 回覆）
        threading.Thread(target=self._process, args=(user_id, text), daemon=True).start()

    def _process(self, user_id: str, text: str):
        try:
            reply = self._run(user_id, text)
            self.broker.publish(OUTBOX_TOPIC, {
                "user_id": user_id,
                "content": reply,
            })
        except Exception as e:
            log.exception(f"[{AGENT_ID}] Error processing message from {user_id[:8]}: {e}")
            self.broker.publish(OUTBOX_TOPIC, {
                "user_id": user_id,
                "content": "抱歉，系統暫時異常，請稍後再試。",
            })

    # ── 五步循環 ──────────────────────────────────────────────────────────────

    def _run(self, user_id: str, user_message: str) -> str:
        situation = self._perceive(user_id, user_message)
        memory_context = self._recall(situation)
        result = self._reason_and_act(user_id, user_message, memory_context)
        self._reflect(situation, result)

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
            log.info(f"[{AGENT_ID}] Recalled: {len(knowledge)} knowledge, {len(episodes)} episodes")
            return "\n\n".join(parts)
        return ""

    def _reason_and_act(self, user_id: str, user_message: str,
                        memory_context: str) -> ActionResult:
        system = SYSTEM_PROMPT
        if memory_context:
            system += f"\n\n{memory_context}"
        role, user_projects = _get_user_role_and_projects(user_id)
        if user_projects:
            names = "、".join(p["name"] for p in user_projects)
            system += f"\n\n## 此使用者的進行中專案\n{names}\n當使用者提到專案時，請以這些「專案名稱」（非 Trello 看板名稱）來辨識與回應。"

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
                            user_id=user_id,
                        )
                    elif block.name == "get_project_photos":
                        result = self._get_project_photos(
                            block.input.get("project_name", ""),
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
        return ActionResult(final_text=final_text, escalated=escalated, tools_used=tools_used)

    def _reflect(self, situation: str, result: ActionResult):
        quality = self._evaluate(result)
        action_summary = f"工具：{result.tools_used}" if result.tools_used else "直接回答"

        self.memory.store_episode(
            situation=situation,
            action=action_summary,
            result=result.final_text[:200] if result.final_text else f"escalated={result.escalated}",
            quality=quality,
        )
        log.info(f"[{AGENT_ID}] Reflected: quality={quality:.1f}, tools={result.tools_used}")

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
        if result.error:     return 0.1
        if result.escalated: return 0.5
        if len(result.final_text) > 100: return 0.8
        if len(result.final_text) > 20:  return 0.6
        return 0.3

    # ── Trello（委託 TrelloAgent via MQTT）────────────────────────────────────

    def _on_trello_reply(self, payload: dict):
        request_id = payload.get("request_id", "")
        if request_id in self._pending:
            event, result = self._pending[request_id]
            result[0] = payload.get("result", "查詢失敗")
            event.set()

    def _get_user_auth(self, user_id: str):
        """Returns (allowed_board_ids, project_map) where project_map is {board_id: project_name}.
        allowed_board_ids: None = no restriction, [] = blocked, [str] = filter.
        For admin/employee, fetch all active projects so trello_agent can label items with project names."""
        role, projects = _get_user_role_and_projects(user_id)
        proj_map = {p["board_id"]: p["name"] for p in projects}
        if role in ("admin", "employee"):
            all_projects = _all_active_projects()
            return None, {**all_projects, **proj_map}
        if role in ("vendor", "customer"):
            return [p["board_id"] for p in projects], proj_map
        return [], {}

    def _query_trello(self, query_type: str, keyword: str = "", user_id: str = "") -> str:
        allowed_board_ids, project_map = self._get_user_auth(user_id) if user_id else (None, {})
        if allowed_board_ids is not None and len(allowed_board_ids) == 0:
            return "您目前沒有工程查詢權限，如有需要請聯繫我們的服務人員。"

        request_id = str(uuid.uuid4())
        reply_topic = f"{TRELLO_REPLY_PREFIX}/{request_id}"

        event = threading.Event()
        result = [None]
        self._pending[request_id] = (event, result)

        self.broker.publish(TRELLO_REQUEST_TOPIC, {
            "request_id": request_id,
            "reply_to": reply_topic,
            "query_type": query_type,
            "keyword": keyword,
            "allowed_board_ids": allowed_board_ids,
            "project_map": project_map,
        })

        try:
            if event.wait(timeout=TRELLO_TIMEOUT):
                return result[0]
            log.info(f"[{AGENT_ID}] Trello request {request_id[:8]} timed out")
            return "查詢 Trello 逾時，請稍後再試。"
        finally:
            self._pending.pop(request_id, None)

    # ── Project Photos ────────────────────────────────────────────────────────

    def _get_project_photos(self, project_name: str) -> str:
        photos = _load_project_photos()
        if not photos:
            return "目前尚未設定工地相簿，請聯繫專人取得照片。"
        keyword = project_name.strip().lower()
        for key, url in photos.items():
            if keyword in key.lower() or key.lower() in keyword:
                return f"相簿連結：{url}"
        keys = "、".join(photos.keys())
        return f"找不到「{project_name}」的相簿。目前有：{keys}"

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
    log.info(f"[{AGENT_ID}] Agent running...")
    broker.loop_forever()
