"""AgentMemory — 三層記憶（工作記憶 + 情節記憶 + 語意記憶）

工作記憶：in-memory LRU + PostgreSQL write-through（重啟後恢復對話）
情節記憶：PostgreSQL episodes 表
語意記憶：PostgreSQL knowledge 表（信心度加權更新）
"""

import threading
from collections import OrderedDict

import psycopg2.extras

from shared.db import db_exec

MAX_HISTORY = 20
MAX_USERS = 500


def _safe_trim(messages: list, limit: int) -> list:
    """截斷對話歷史，確保開頭不是孤立的 tool_result（避免 Anthropic 400）。"""
    trimmed = messages[-limit:]
    # 若第一條 user 訊息的 content 是 tool_result list，代表對應的 tool_use 被切掉了
    # 持續丟棄開頭直到序列合法
    while trimmed:
        first = trimmed[0]
        content = first.get("content", "")
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        ):
            trimmed = trimmed[1:]  # 丟掉這條孤立的 tool_result
        else:
            break
    return trimmed


class AgentMemory:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._working: OrderedDict = OrderedDict()  # thread_id → {"messages": [...]}
        self._lock = threading.Lock()

    # ── 工作記憶 ─────────────────────────────────────────────────────────────

    def get_working(self, thread_id: str) -> list:
        with self._lock:
            entry = self._working.get(thread_id)
            if entry:
                self._working.move_to_end(thread_id)
                return list(entry["messages"])

        # Cache miss：從 DB 載入（重啟後恢復對話）
        def load(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT messages FROM working_memory WHERE agent_id = %s AND thread_id = %s",
                    (self.agent_id, thread_id),
                )
                row = cur.fetchone()
                return row[0] if row else None

        messages = db_exec(load)
        if messages:
            with self._lock:
                if len(self._working) >= MAX_USERS:
                    self._working.popitem(last=False)
                self._working[thread_id] = {"messages": messages}
            return list(messages)
        return []

    def append_working(self, thread_id: str, new_messages: list):
        with self._lock:
            if thread_id in self._working:
                entry = self._working[thread_id]
                self._working.move_to_end(thread_id)
            else:
                if len(self._working) >= MAX_USERS:
                    self._working.popitem(last=False)
                entry = {"messages": []}
                self._working[thread_id] = entry
            entry["messages"] = _safe_trim(entry["messages"] + new_messages, MAX_HISTORY)
            updated = list(entry["messages"])

        def save(conn):
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO working_memory (agent_id, thread_id, messages)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (agent_id, thread_id) DO UPDATE SET
                        messages   = EXCLUDED.messages,
                        updated_at = now()
                    """,
                    (self.agent_id, thread_id, psycopg2.extras.Json(updated)),
                )

        db_exec(save)

    # ── 情節記憶 ─────────────────────────────────────────────────────────────

    def store_episode(self, situation: str, action: str, result: str, quality: float):
        def save(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO episodes (agent_id, situation, action, result, quality) VALUES (%s,%s,%s,%s,%s)",
                    (self.agent_id, situation, action, result, quality),
                )
        db_exec(save)

    def recall_episodes(self, situation: str, top_k: int = 3) -> list:
        def load(conn):
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT situation, action, result, quality
                    FROM episodes
                    WHERE agent_id = %s AND situation ILIKE %s
                    ORDER BY quality DESC, created_at DESC
                    LIMIT %s
                    """,
                    (self.agent_id, f"%{situation[:30]}%", top_k),
                )
                return cur.fetchall()
        return db_exec(load) or []

    # ── 語意記憶 ─────────────────────────────────────────────────────────────

    def store_knowledge(self, fact: str, confidence: float):
        def save(conn):
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO knowledge (agent_id, fact, confidence, source_count)
                    VALUES (%s, %s, %s, 1)
                    ON CONFLICT (agent_id, fact) DO UPDATE SET
                        confidence   = (knowledge.confidence * knowledge.source_count + %s)
                                       / (knowledge.source_count + 1),
                        source_count = knowledge.source_count + 1,
                        updated_at   = now()
                    """,
                    (self.agent_id, fact, confidence, confidence),
                )
        db_exec(save)

    def get_knowledge(self, topic: str) -> list:
        def load(conn):
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT fact, confidence FROM knowledge
                    WHERE agent_id = %s AND fact ILIKE %s AND confidence > 0.5
                    ORDER BY confidence DESC LIMIT 5
                    """,
                    (self.agent_id, f"%{topic[:30]}%"),
                )
                return cur.fetchall()
        return db_exec(load) or []
