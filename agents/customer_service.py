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
from trello_line_notifier import (
    TAIPEI, send_line, send_flex,
    get_card, parse_tag,
    set_checkitem_state, set_card_due_complete, add_card_comment,
    _internal_recipients,
)
from shared.guide import guide_messages, GUIDE_KEYWORDS

TRELLO_INVALIDATE_TOPIC = "agents/trello/invalidate"

AGENT_ID = "customer_service"
INBOX_TOPIC = f"agents/{AGENT_ID}/inbox"
OUTBOX_TOPIC = "gateway/outbox"
TRELLO_REQUEST_TOPIC = "agents/trello/requests"
TRELLO_REPLY_PREFIX = "agents/trello/responses"
TRELLO_TIMEOUT = 30  # 秒

MODEL = "claude-haiku-4-5-20251001"
MAX_TOOL_TURNS = 5
MAX_TOKENS = 2048
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
        reply_token = payload.get("reply_token")

        # 提醒卡片按鈕（完成/取消、主管確認/退回）— 結構化動作，不進 Claude loop
        if payload.get("kind") == "postback":
            pb = payload.get("postback", {})
            log.info(f"[{AGENT_ID}] Postback from {user_id[:8]}: {pb}")
            threading.Thread(target=self._process_postback, args=(user_id, pb, reply_token), daemon=True).start()
            return

        text = payload.get("text", "")
        if not text:
            return
        # 關鍵字「使用說明」備援入口（Rich Menu 圖片缺失時仍可觸發）
        if text.strip() in GUIDE_KEYWORDS:
            log.info(f"[{AGENT_ID}] Guide keyword from {user_id[:8]}")
            threading.Thread(target=self._handle_guide, args=(user_id, reply_token), daemon=True).start()
            return
        log.info(f"[{AGENT_ID}] Received from {user_id[:8]}: {text[:60]}")
        # 背景執行，避免阻塞 MQTT loop（event.wait 需要 loop 持續運作才能收到 Trello 回覆）
        threading.Thread(target=self._process, args=(user_id, text, reply_token), daemon=True).start()

    def _process(self, user_id: str, text: str, reply_token: str | None = None):
        try:
            reply = self._run(user_id, text)
            self.broker.publish(OUTBOX_TOPIC, {
                "user_id": user_id,
                "content": reply,
                "reply_token": reply_token,
            })
        except Exception as e:
            log.exception(f"[{AGENT_ID}] Error processing message from {user_id[:8]}: {e}")
            self.broker.publish(OUTBOX_TOPIC, {
                "user_id": user_id,
                "content": "抱歉，系統暫時異常，請稍後再試。",
                "reply_token": reply_token,
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
            system += (
                f"\n\n## 此使用者身分與專案（系統已確認，請勿再詢問他是誰）\n"
                f"此使用者目前進行中的專案：{names}\n"
                f"- 當他說「我／我的案子／我有哪些工作／我這邊」時，即指上述專案。\n"
                f"- 請直接用 query_trello 查這些專案作答，切勿反問他是誰、也不要他報名字或案場。\n"
                f"- 請以「專案名稱」（非 Trello 看板名稱）辨識與回應。\n"
                f"- 若過往對話或範例與此衝突，以本段為準。"
            )

        history = self.memory.get_working(user_id)
        new_messages = [{"role": "user", "content": user_message}]
        escalated = False
        final_text = ""
        tools_used = []

        for _ in range(MAX_TOOL_TURNS):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=history + new_messages,
                tools=TOOLS,
            )
            new_messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})

            # end_turn 為正常結束；max_tokens 代表答案被截斷，但仍要保留已生成的文字，
            # 否則 final_text 會留空而誤觸「已通知專人跟進」fallback。
            if response.stop_reason in ("end_turn", "max_tokens"):
                for block in response.content:
                    if hasattr(block, "text") and block.text:
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
        # 未呼叫任何工具的回答（純文字／反問身分）一律低於「成功」門檻(>0.7)，
        # 避免「沒查就回」被存成成功 episode 並被 _recall 回放而自我增強。
        if not result.tools_used:
            return 0.6 if len(result.final_text) > 20 else 0.3
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


    # ── 工項完成狀態更新（提醒卡片按鈕 / 主管追認）──────────────────────────────

    def _reply(self, user_id: str, content: str, reply_token: str | None):
        self.broker.publish(OUTBOX_TOPIC, {
            "user_id": user_id, "content": content, "reply_token": reply_token,
        })

    def _handle_guide(self, user_id: str, reply_token: str | None, pb: dict | None = None):
        """LINE 對話內線上說明：主題選單 / 單一主題 / 完整手冊（依角色）。走 Reply API。"""
        _display, _alias, role = self._user_identity(user_id)  # 查無記錄 → visitor
        msgs = guide_messages(role, pb)
        if not msgs:
            self._reply(user_id, "目前沒有可用的使用說明，請聯繫服務人員。", reply_token)
            return
        self.broker.publish(OUTBOX_TOPIC, {
            "user_id": user_id, "messages": msgs, "reply_token": reply_token,
        })

    def _invalidate_trello_cache(self):
        try:
            self.broker.publish(TRELLO_INVALIDATE_TOPIC, {"ts": datetime.now(TAIPEI).isoformat()})
        except Exception:
            pass

    def _user_identity(self, user_id: str) -> tuple:
        """(display_name, alias_name, role) from line_users."""
        def _q(conn):
            with conn.cursor() as cur:
                cur.execute("SELECT display_name, alias_name, role FROM line_users WHERE line_id=%s", (user_id,))
                return cur.fetchone()
        try:
            r = db_exec(_q)
        except Exception:
            r = None
        if not r:
            return user_id[:8], None, "visitor"
        if isinstance(r, dict):
            return (r.get("display_name") or user_id[:8], r.get("alias_name"), r.get("role") or "visitor")
        return (r[0] or user_id[:8], r[1], r[2] or "visitor")

    def _resolve_target(self, card: dict, source: str, checkitem_id: str | None) -> tuple:
        """(names, label, currently_complete) for the target work item, or (None, None, None)."""
        if source == "checklist":
            for cl in card.get("checklists", []):
                for it in cl.get("checkItems", []):
                    if it.get("id") == checkitem_id:
                        parsed = parse_tag(it["name"])
                        if not parsed:
                            return None, None, None
                        names, _, _, _, label = parsed
                        return names, (label or it["name"]), (it.get("state") == "complete")
            return None, None, None
        parsed = parse_tag((card.get("desc") or "").split("\n")[0])
        if not parsed:
            return None, None, None
        names, _, _, _, label = parsed
        return names, (label or card.get("name", "")), bool(card.get("dueComplete"))

    def _process_postback(self, user_id: str, pb: dict, reply_token: str | None):
        try:
            op = pb.get("o")
            if op in ("complete", "incomplete"):
                self._handle_status_update(user_id, pb, reply_token)
            elif op in ("confirm", "reject"):
                self._handle_confirmation(user_id, pb, reply_token)
            elif op == "guide":
                self._handle_guide(user_id, reply_token, pb)
            else:
                self._reply(user_id, "未知動作。", reply_token)
        except Exception as e:
            log.exception(f"[{AGENT_ID}] postback error: {e}")
            self._reply(user_id, "處理時發生錯誤，請稍後再試。", reply_token)

    def _handle_status_update(self, user_id: str, pb: dict, reply_token: str | None):
        op = pb.get("o")
        card_id = pb.get("c", "")
        checkitem_id = pb.get("i") or None
        source = pb.get("s", "card")
        board_id = pb.get("b", "")
        complete = (op == "complete")
        display, alias, role = self._user_identity(user_id)
        allowed_board_ids, _ = self._get_user_auth(user_id)

        try:
            card = get_card(card_id)
        except Exception:
            self._reply(user_id, "找不到該工項卡片，請稍後再試。", reply_token)
            return
        names, label, cur_complete = self._resolve_target(card, source, checkitem_id)
        if names is None:
            self._reply(user_id, "找不到該工項，可能已被移除。", reply_token)
            return
        # 看板授權（None=不限；list=限定；[]=封鎖）
        if allowed_board_ids is not None and card.get("idBoard", "") not in set(allowed_board_ids):
            self._reply(user_id, "您沒有此工地的操作權限。", reply_token)
            return
        is_supervisor = role in ("admin", "employee")
        is_owner = bool(alias) and alias.lower() in [n.lower() for n in names]
        if not (is_supervisor or is_owner):
            self._reply(user_id, "僅該工項負責人或主管可標記，您目前無權限。", reply_token)
            return
        act = "完成" if complete else "取消完成"
        if cur_complete == complete:
            self._reply(user_id, f"「{label}」已是{'完成' if complete else '未完成'}狀態。", reply_token)
            return
        # 寫入 Trello
        if source == "checklist":
            sc, ok = set_checkitem_state(card_id, checkitem_id, complete)
        else:
            sc, ok = set_card_due_complete(card_id, complete)
        if not ok:
            self._reply(user_id, f"更新失敗（Trello {sc}），請稍後再試或至看板操作。", reply_token)
            return
        self._invalidate_trello_cache()
        now = datetime.now(TAIPEI).strftime("%Y/%m/%d %H:%M")
        who = f"{display}（{alias}）" if alias else display
        suffix = "" if is_supervisor else "（待主管確認）"
        add_card_comment(card_id, f"🤖 LINE：{who} 於 {now} 標記「{label}」為{act}{suffix}")
        if is_supervisor:
            self._reply(user_id, f"已將「{label}」標記為{act}。", reply_token)
            return
        # 廠商：暫定生效 + pending + 通知主管
        cid = self._insert_pending(board_id, card_id, checkitem_id, source, label, op, user_id, alias)
        if cid is not None:
            self._notify_supervisors(label, who, act, cid)
        self._reply(user_id, f"已暫定將「{label}」標記為{act}，將通知主管確認。", reply_token)

    def _handle_confirmation(self, user_id: str, pb: dict, reply_token: str | None):
        cid = pb.get("cid")
        display, _alias, role = self._user_identity(user_id)
        if role not in ("admin", "employee"):
            self._reply(user_id, "僅主管可確認/退回。", reply_token)
            return
        row = self._load_pending(cid)
        if not row:
            self._reply(user_id, "查無此待確認項目。", reply_token)
            return
        if row["status"] != "pending":
            self._reply(user_id, "此項目已處理。", reply_token)
            return
        label, card_id, checkitem_id = row["label"], row["card_id"], row["checkitem_id"]
        source, target_state = row["source"], row["target_state"]
        now = datetime.now(TAIPEI).strftime("%Y/%m/%d %H:%M")
        if pb.get("o") == "confirm":
            self._resolve_pending(cid, "confirmed", user_id)
            add_card_comment(card_id, f"✅ LINE：主管 {display} 於 {now} 確認「{label}」")
            self._reply(user_id, f"已確認「{label}」。", reply_token)
        else:  # reject → 還原 Trello 為 claim 前狀態
            revert_complete = (target_state != "complete")
            if source == "checklist":
                set_checkitem_state(card_id, checkitem_id, revert_complete)
            else:
                set_card_due_complete(card_id, revert_complete)
            self._invalidate_trello_cache()
            self._resolve_pending(cid, "rejected", user_id)
            add_card_comment(card_id, f"❌ LINE：主管 {display} 於 {now} 退回「{label}」，已還原")
            self._reply(user_id, f"已退回「{label}」並還原狀態。", reply_token)

    def _insert_pending(self, board_id, card_id, checkitem_id, source, label, target_state, claimer_user_id, claimer_alias):
        def _q(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO task_confirmations "
                    "(board_id, card_id, checkitem_id, source, label, target_state, claimer_user_id, claimer_alias) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (board_id, card_id, checkitem_id, source, label, target_state, claimer_user_id, claimer_alias))
                r = cur.fetchone()
                return r["id"] if isinstance(r, dict) else r[0]
        try:
            return db_exec(_q)
        except Exception:
            return None

    def _load_pending(self, cid):
        def _q(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, board_id, card_id, checkitem_id, source, label, target_state, status "
                    "FROM task_confirmations WHERE id=%s", (cid,))
                return cur.fetchone()
        try:
            r = db_exec(_q)
        except Exception:
            r = None
        if not r:
            return None
        if isinstance(r, dict):
            return r
        keys = ["id", "board_id", "card_id", "checkitem_id", "source", "label", "target_state", "status"]
        return dict(zip(keys, r))

    def _resolve_pending(self, cid, status, confirmer_user_id):
        def _q(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE task_confirmations SET status=%s, confirmer_user_id=%s, resolved_at=now() "
                    "WHERE id=%s AND status='pending'", (status, confirmer_user_id, cid))
                return cur.rowcount
        try:
            return db_exec(_q)
        except Exception:
            return 0

    def _notify_supervisors(self, label, who, act, cid):
        supervisors = _internal_recipients()
        flex = self._confirm_flex(label, who, act, cid)
        for uid in supervisors:
            if not uid:
                continue
            try:
                send_flex(uid, flex, f"待確認：{label}")
            except Exception as e:
                log.warning(f"[{AGENT_ID}] notify supervisor failed: {e}")

    def _confirm_flex(self, label, who, act, cid):
        return {
            "type": "bubble", "size": "mega",
            "header": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": "意念情境・待主管確認", "size": "xs", "color": "#AAAAAA"},
                {"type": "text", "text": f"廠商標記{act}", "weight": "bold", "size": "md", "color": "#EF6C00", "margin": "sm"}]},
            "body": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": label, "weight": "bold", "size": "sm", "color": "#1A1A1A", "wrap": True},
                {"type": "text", "text": f"由 {who} 標記", "size": "xs", "color": "#666666", "wrap": True, "margin": "sm"},
                {"type": "box", "layout": "horizontal", "margin": "lg", "spacing": "sm", "contents": [
                    {"type": "button", "style": "primary", "color": "#388E3C", "height": "sm",
                     "action": {"type": "postback", "label": "✅ 確認", "data": f"o=confirm&cid={cid}", "displayText": "確認"}},
                    {"type": "button", "style": "secondary", "height": "sm",
                     "action": {"type": "postback", "label": "❌ 退回", "data": f"o=reject&cid={cid}", "displayText": "退回"}}]}]},
        }


if __name__ == "__main__":
    broker = MQTTBroker(client_id=AGENT_ID)
    agent = CustomerServiceAgent(broker)
    broker.connect()
    agent.start()
    log.info(f"[{AGENT_ID}] Agent running...")
    broker.loop_forever()
