# True AI Agent Architecture Design

## 設計原則

### 什麼是「真正的 AI Agent」

```
Rule-based function call:
  input → 固定邏輯 → output

LLM function call（無記憶）:
  input → LLM 推理（單次）→ output   ← 只是聰明的 function，不是 Agent

True AI Agent:
  input + 記憶 + 目標 → 推理 → 行動 → 觀察 → 更新記憶 → 下一步
```

關鍵條件：
1. **獨立 Process** — 長期運行，有自己的生命週期
2. **三層記憶** — 工作記憶 + 情節記憶 + 語意記憶
3. **學習循環** — `reflect()` 讓 Agent 從每次行動中提煉知識
4. **訊息通訊** — Agent 之間透過 MQTT 解耦，不直接呼叫對方

> **沒有 `reflect()` 的 Agent 只是有記憶的 chatbot，不會進化。**

---

## 整體架構

```
LINE Platform
     │  HTTPS POST /webhook
     ▼
┌────────────────────┐
│   LINE Gateway     │  純 web server，不含 AI 邏輯
│   (FastAPI)        │  職責：驗簽、解析 event、發布到 MQTT
└────────────────────┘
          │  MQTT publish: agents/customer_service/inbox
          ▼
     MQTT Broker（NATS 或 Mosquitto）
          │
     ┌────┴─────────────────────────────────┐
     │                                      │
     ▼                                      ▼
┌──────────────────┐              ┌──────────────────┐
│ Customer Service │              │  Trello Agent    │
│ Agent            │◄────MQTT────►│                  │
│ ┌──────────────┐ │              │ ┌──────────────┐ │
│ │    Memory    │ │              │ │    Memory    │ │
│ │  PostgreSQL  │ │              │ │  PostgreSQL  │ │
│ └──────────────┘ │              │ └──────────────┘ │
└──────────────────┘              └──────────────────┘
          │                                │
          └──────────── MQTT ──────────────┘
                         │
                    ┌────▼─────────────────┐
                    │  Notification Agent  │
                    │  ┌──────────────┐    │
                    │  │    Memory    │    │
                    │  │  PostgreSQL  │    │
                    │  └──────────────┘    │
                    └──────────────────────┘
                         │
                    MQTT publish: gateway/outbox
                         │
                    LINE Gateway → LINE Push API → 客戶
```

### 多 Channel 延伸性

Gateway 層負責協議轉換，Agent 完全不知道訊息從哪來：

```
LINE Gateway    ─┐
Web Chat Gateway ─┼──► MQTT ──► Customer Service Agent
Email Gateway   ─┘

統一 payload 格式：
{
    "user_id":   "line_Uxxxxxxx" | "web_session_xxx",
    "text":      "...",
    "source":    "line" | "web" | "email",
    "timestamp": "..."
}
```

---

## Agent 內部設計

### 五步循環

每次收到訊息，Agent 執行：

```
Inbox (MQTT)
     │
     ▼
1. Perceive    ← 理解收到的訊息，轉成結構化 situation
     │
     ▼
2. Recall      ← 從 DB 撈相關情節記憶 + 語意知識
     │
     ▼
3. Reason      ← Claude API（system prompt 注入記憶 context）
     │            agentic loop with tools
     ▼
4. Act         ← 執行工具 / 發布回覆到 MQTT
     │
     ▼
5. Reflect     ← 評估結果品質，寫入 DB   ← 學習發生在這裡
```

### 學習效果範例

```
Day 1：
  客戶問「王先生進度」
  → 沒有經驗，用 query_type=all 廣撒網
  → 找到了，quality=0.8
  → reflect 寫入：「含姓名的問題，用 specific+keyword 最有效」

Day 3：
  另一客戶問「陳小姐工程怎樣了」
  → recall 找到上面的知識
  → 直接用 specific+keyword=陳小姐
  → 更快，quality=0.9，信心度提升

Day 7：
  客戶問「我的地板什麼時候鋪」
  → recall：「姓名查詢用 specific」
  → 但這次沒有姓名，Agent 主動問：「請問您是哪位客戶？」
  → reflect 寫入：「缺少姓名時，先釐清身份再查詢」
```

---

## 記憶系統設計

### 三層記憶

| 層次 | 名稱 | 生命週期 | 儲存位置 | 說明 |
|------|------|---------|---------|------|
| L1 | 工作記憶 | 任務結束清空 | In-memory（dict） | 當前對話的 Claude messages array |
| L2 | 情節記憶 | 永久 | PostgreSQL `episodes` | 每次行動的完整經驗紀錄 |
| L3 | 語意記憶 | 永久（持續更新） | PostgreSQL `knowledge` | 從多次情節提煉出的通用規律 |

### DB Schema

```sql
-- 每個 Agent 有自己的 schema（或共用 DB 加 agent_id 欄位）

CREATE TABLE episodes (
    id           SERIAL PRIMARY KEY,
    agent_id     TEXT NOT NULL,
    situation    TEXT NOT NULL,         -- 當時面對什麼
    action       TEXT NOT NULL,         -- 做了什麼（摘要）
    result       TEXT NOT NULL,         -- 結果是什麼
    quality      FLOAT NOT NULL,        -- 0.0~1.0
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON episodes (agent_id, created_at DESC);

-- 進階：加向量欄位做語意搜尋（pgvector）
-- ALTER TABLE episodes ADD COLUMN embedding vector(1536);


CREATE TABLE knowledge (
    id           SERIAL PRIMARY KEY,
    agent_id     TEXT NOT NULL,
    fact         TEXT NOT NULL,
    confidence   FLOAT NOT NULL DEFAULT 0.5,   -- 0.0~1.0，多次經驗加權平均
    source_count INTEGER NOT NULL DEFAULT 1,   -- 從幾次情節提煉
    updated_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (agent_id, fact)
);

-- 工作記憶（可選：持久化以支援 Agent 重啟後恢復對話）
CREATE TABLE working_memory (
    id           SERIAL PRIMARY KEY,
    agent_id     TEXT NOT NULL,
    thread_id    TEXT NOT NULL,          -- 對應 LINE user_id
    messages     JSONB NOT NULL,         -- Claude messages array
    updated_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (agent_id, thread_id)
);
CREATE INDEX ON working_memory (agent_id, thread_id);
```

### Memory 類別

```python
class AgentMemory:
    def __init__(self, agent_id: str, db: Connection):
        self.agent_id = agent_id
        self.db = db
        self.working: dict[str, list] = {}  # thread_id → messages

    # ── 工作記憶 ─────────────────────────────────────
    def get_working(self, thread_id: str) -> list:
        return self.working.get(thread_id, [])

    def append_working(self, thread_id: str, role: str, content):
        if thread_id not in self.working:
            self.working[thread_id] = []
        self.working[thread_id].append({"role": role, "content": content})
        self.working[thread_id] = self.working[thread_id][-20:]  # 保留最近 20 則

    # ── 情節記憶 ─────────────────────────────────────
    def store_episode(self, situation: str, action: str,
                      result: str, quality: float):
        self.db.execute("""
            INSERT INTO episodes (agent_id, situation, action, result, quality)
            VALUES (%s, %s, %s, %s, %s)
        """, (self.agent_id, situation, action, result, quality))

    def recall_episodes(self, situation: str, top_k=3) -> list:
        # 基礎版：keyword 搜尋
        # 進階版：pgvector 語意搜尋
        return self.db.query("""
            SELECT situation, action, result, quality
            FROM episodes
            WHERE agent_id = %s AND situation ILIKE %s
            ORDER BY quality DESC, created_at DESC
            LIMIT %s
        """, (self.agent_id, f"%{situation[:30]}%", top_k))

    # ── 語意記憶 ─────────────────────────────────────
    def store_knowledge(self, fact: str, confidence: float):
        # 重複出現的知識，信心度加權平均自動上升
        self.db.execute("""
            INSERT INTO knowledge (agent_id, fact, confidence, source_count)
            VALUES (%s, %s, %s, 1)
            ON CONFLICT (agent_id, fact) DO UPDATE SET
                confidence   = (knowledge.confidence * knowledge.source_count + %s)
                               / (knowledge.source_count + 1),
                source_count = knowledge.source_count + 1,
                updated_at   = now()
        """, (self.agent_id, fact, confidence, confidence))

    def get_knowledge(self, topic: str) -> list:
        return self.db.query("""
            SELECT fact, confidence
            FROM knowledge
            WHERE agent_id = %s AND fact ILIKE %s AND confidence > 0.5
            ORDER BY confidence DESC
            LIMIT 5
        """, (self.agent_id, f"%{topic[:30]}%"))
```

---

## Gateway 設計

```python
# gateway/line_gateway.py
# 純 I/O，不含任何 AI 邏輯

@app.route("/webhook", methods=["POST"])
def webhook():
    if not verify_signature(request.get_data(),
                             request.headers.get("X-Line-Signature", "")):
        abort(400)

    for event in request.get_json().get("events", []):
        if event.get("type") != "message":
            continue
        if event["message"].get("type") != "text":
            continue

        broker.publish("agents/customer_service/inbox", {
            "user_id":   event["source"]["userId"],
            "text":      event["message"]["text"],
            "timestamp": event["timestamp"],
            "source":    "line",
        })

    return "OK"   # 立即回，不等 Agent


@broker.on("gateway/outbox")
def on_agent_reply(payload: dict):
    send_line(payload["user_id"], payload["content"])
```

---

## Agent 基底類別

```python
# agents/base/brain.py

class AgentBrain:
    def __init__(self, agent_id: str, system_prompt: str,
                 tools: list, memory: AgentMemory):
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.tools = tools
        self.memory = memory
        self.client = anthropic.Anthropic()

    def process(self, msg: AgentMessage) -> AgentMessage | None:
        thread_id = msg.thread_id
        try:
            situation       = self._perceive(msg)
            memory_context  = self._recall(situation)
            result          = self._reason_and_act(thread_id, situation, memory_context)
            self._reflect(situation, result)
            return AgentMessage(
                from_agent=self.agent_id,
                to_agent=msg.from_agent,
                thread_id=thread_id,
                content=result.final_text,
            )
        except Exception as e:
            self._reflect_on_failure(msg.content, str(e))
            raise

    def _perceive(self, msg: AgentMessage) -> str:
        return f"來自 {msg.from_agent}：{msg.content}"

    def _recall(self, situation: str) -> str:
        knowledge = self.memory.get_knowledge(situation)
        episodes  = self.memory.recall_episodes(situation)
        parts = []
        if knowledge:
            parts.append("【已知規律】\n" + "\n".join(
                f"・{k['fact']}（信心：{k['confidence']:.0%}）"
                for k in knowledge
            ))
        if episodes:
            parts.append("【過去經驗】\n" + "\n".join(
                f"・{e['situation'][:40]}... → {'✓' if e['quality'] > 0.7 else '✗'}"
                for e in episodes
            ))
        return "\n\n".join(parts)

    def _reason_and_act(self, thread_id: str, situation: str,
                         memory_context: str) -> ActionResult:
        system = self.system_prompt
        if memory_context:
            system += f"\n\n{memory_context}"

        self.memory.append_working(thread_id, "user", situation)

        for _ in range(MAX_TOOL_TURNS):
            resp = self.client.messages.create(
                model=MODEL,
                system=system,
                messages=self.memory.get_working(thread_id),
                tools=self.tools,
            )
            self.memory.append_working(thread_id, "assistant", resp.content)

            if resp.stop_reason == "end_turn":
                final_text = next(
                    (b.text for b in resp.content if hasattr(b, "text")), ""
                )
                return ActionResult(final_text=final_text)

            if resp.stop_reason == "tool_use":
                tool_results, escalated = self._execute_tools(resp.content)
                self.memory.append_working(thread_id, "user", tool_results)
                if escalated:
                    return ActionResult(final_text="", escalated=True)

        return ActionResult(final_text="", error="max_turns_reached")

    def _reflect(self, situation: str, result: ActionResult):
        quality = self._evaluate(result)

        self.memory.store_episode(
            situation=situation,
            action=self._summarize_actions(result),
            result=result.final_text[:200],
            quality=quality,
        )

        if quality > 0.8:
            insight = self._extract_insight(situation, result, "success")
            self.memory.store_knowledge(insight, confidence=quality)
        elif quality < 0.3:
            insight = self._extract_insight(situation, result, "failure")
            self.memory.store_knowledge(f"避免：{insight}", confidence=1 - quality)

    def _evaluate(self, result: ActionResult) -> float:
        if result.error:     return 0.1
        if result.escalated: return 0.5
        if len(result.final_text) > 50: return 0.8
        return 0.6
```

---

## 訊息格式

```python
@dataclass
class AgentMessage:
    from_agent: str
    to_agent:   str
    thread_id:  str        # 同一用戶的對話串（LINE user_id）
    content:    str
    msg_id:     str = field(default_factory=lambda: str(uuid4()))
    timestamp:  float = field(default_factory=time.time)
    metadata:   dict = field(default_factory=dict)

# MQTT Topic 規範
# agents/{agent_id}/inbox     點對點
# agents/*/events              廣播
# gateway/outbox               回覆給 Gateway
```

---

## 檔案結構

```
linebot/
├── gateway/
│   └── line_gateway.py        # 純 I/O，驗簽 + MQTT publish/subscribe
│
├── agents/
│   ├── base/
│   │   ├── brain.py           # AgentBrain（五步循環）
│   │   ├── memory.py          # AgentMemory（三層 + DB）
│   │   └── message.py         # AgentMessage dataclass
│   │
│   ├── customer_service.py    # 客服 Agent
│   ├── trello_agent.py        # Trello 查詢 Agent
│   └── notify_agent.py        # 通知 Agent（現有 CronJob 邏輯移入）
│
├── shared/
│   ├── tools.py               # query_trello, escalate_to_manager 定義
│   ├── broker.py              # MQTT wrapper（publish/subscribe）
│   └── db.py                  # PostgreSQL connection pool
│
├── migrations/
│   └── 001_init.sql           # episodes, knowledge, working_memory schema
│
├── linebot_server.py          # 現有（過渡期保留，最終由 gateway/ 取代）
└── trello_line_notifier.py    # 現有（CronJob 邏輯，最終整合進 notify_agent）
```

---

## 實作路線圖

```
Phase 1：記憶持久化                                    ✅ 完成（2026-05-01）
  ├── 建立 PostgreSQL schema（migrations/001_init.sql）  ✅
  ├── 把 linebot_server.py 的 _history（in-memory）改為寫 DB  ✅
  └── 驗證：重啟 server 後對話記憶還在                  ✅

Infra：PostgreSQL + MQTT 部署（jgu4 cluster）          ✅ 完成（2026-05-03）
  ├── extras-postgres Kustomization 上線，pod 1/1 Running  ✅
  ├── DB schema 建立（episodes, knowledge, working_memory）  ✅
  └── extras-mqtt Kustomization 上線，namespace: mqtt    ✅

Phase 2：Gateway 分離                                  ✅ 完成（2026-05-03）
  ├── 建立 gateway/line_gateway.py（純 I/O）             ✅
  ├── 引入 MQTT broker（Mosquitto，已在 jgu4 上線）       ✅
  └── linebot_server.py 的 AI 邏輯移入 agents/customer_service.py  ✅

Phase 3：真正的 Agent 循環                              ✅ 完成（2026-05-03）
  ├── 實作 AgentBrain 五步循環                           ✅
  ├── 實作 reflect()，開始寫入情節記憶和語意知識           ✅
  └── 觀察 Agent 是否展現學習行為                         ✅（recall 有讀到 1 knowledge, 2 episodes）

Phase 4：拆出子 Agent                                   ✅ 完成（2026-05-04）
  ├── TrelloAgent 成為獨立 process（agents/trello_agent.py）  ✅
  ├── MQTT request/reply pattern（wildcard sub + pending dict）  ✅
  └── 三個 Deployment 均在 jgu4 Running                   ✅
  └── NotifyAgent 整合現有 CronJob 邏輯                   ⬜ 未做

Phase 5：語意搜尋（視需求）                              ⬜
  ├── pgvector 擴充
  ├── episodes 加 embedding 欄位
  └── recall_episodes 改為向量相似度搜尋
```

---

## 關於記憶媒介的選擇

> **為什麼用 DB 而非檔案？**

Claude Code 本身用檔案（`/memory/*.md`）作為記憶，在單用戶、長 context 的場景下非常有效。

linebot 選擇 DB 的原因：
- **多用戶並發**：同時有多個客戶的對話，需要 thread-safe 的讀寫
- **結構化查詢**：可以按 quality、agent_id、timestamp 篩選
- **信心度更新**：`knowledge.confidence` 需要原子性的加權計算
- **未來向量搜尋**：pgvector 直接在 DB 內做語意搜尋，不需要額外服務

> 記憶的本質不變（工作記憶 + 情節 + 語意），只是儲存媒介從檔案換成 DB。

---

## k8scc Claude Code — DB-backed Memory 設計

### 背景

`k8scc` 是一個 web 終端容器（ttyd + Claude Code CLI），讓開發者在外出時透過瀏覽器存取 Claude Code。
問題：Claude Code 預設把 auto-memory 寫在 `/home/claude/.claude/projects/*/memory/*.md`，容器重建後記憶全清。

### 解決方案概覽

兩層機制並存：

| 層 | 機制 | 儲存 | 說明 |
|---|------|------|------|
| 自動記憶 | Claude Code auto-memory | PVC 掛載 `/home/claude/.claude` | 重建容器記憶保留；寫 `.md` 檔案 |
| 明確記憶 | MCP Memory Server | PostgreSQL（同 linebot agent DB） | 呼叫 `remember()`/`recall()` 明確寫入 |

### 方案一：PVC 掛載（最簡單）

把整個 `/home/claude/.claude` 掛到 PersistentVolumeClaim：

```yaml
# k8s Deployment patch（jg-jiahd repo）
volumes:
  - name: claude-config
    persistentVolumeClaim:
      claimName: claude-code-config

containers:
  - name: k8scc
    volumeMounts:
      - name: claude-config
        mountPath: /home/claude/.claude
```

優點：零程式碼改動，auto-memory 即持久。
缺點：仍是 .md 檔案，無法跨工作區結構化查詢。

### 方案二：MCP Memory Server（進階）

在容器內啟動一個 MCP server，提供 `remember` / `recall` / `forget` 工具，後端接 PostgreSQL。

#### Dockerfile 調整

```diff
 RUN apt-get update && apt-get install -y \
     git curl wget bash openssh-client procps \
     ca-certificates dbus libsecret-1-0 gnome-keyring \
-    python3 \
+    python3 python3-pip \
     && rm -rf /var/lib/apt/lists/*

+# Install MCP server deps
+RUN pip3 install --break-system-packages psycopg2-binary mcp
+
+COPY memory_mcp_server.py /usr/local/bin/memory_mcp_server.py
+RUN chmod +x /usr/local/bin/memory_mcp_server.py
```

#### MCP Server 核心

```python
# /usr/local/bin/memory_mcp_server.py
import os, psycopg2, json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

app = Server("memory")
DB_URL = os.environ["DATABASE_URL"]


def get_conn():
    return psycopg2.connect(DB_URL)


@app.tool()
async def remember(fact: str, confidence: float = 0.8) -> str:
    """儲存一條知識到長期記憶"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO knowledge (agent_id, fact, confidence, source_count)
            VALUES ('claude_code', %s, %s, 1)
            ON CONFLICT (agent_id, fact) DO UPDATE SET
                confidence   = (knowledge.confidence * knowledge.source_count + %s)
                               / (knowledge.source_count + 1),
                source_count = knowledge.source_count + 1,
                updated_at   = now()
        """, (fact, confidence, confidence))
    return f"已記憶：{fact}"


@app.tool()
async def recall(topic: str) -> str:
    """從長期記憶搜尋相關知識"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT fact, confidence FROM knowledge
            WHERE agent_id = 'claude_code'
              AND fact ILIKE %s AND confidence > 0.4
            ORDER BY confidence DESC LIMIT 10
        """, (f"%{topic}%",))
        rows = cur.fetchall()
    if not rows:
        return f"找不到關於「{topic}」的記憶"
    return "\n".join(f"・{f}（{c:.0%}）" for f, c in rows)


@app.tool()
async def forget(fact: str) -> str:
    """刪除特定記憶"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            DELETE FROM knowledge
            WHERE agent_id = 'claude_code' AND fact ILIKE %s
        """, (f"%{fact}%",))
        deleted = cur.rowcount
    return f"已刪除 {deleted} 條記憶"


if __name__ == "__main__":
    import asyncio
    asyncio.run(stdio_server(app))
```

#### entrypoint.sh 調整

```bash
# 若 DATABASE_URL 有設定，則把 MCP server 注入 settings.json
if [ -n "${DATABASE_URL}" ]; then
    python3 - <<'PYEOF'
import json, os

settings_path = "/home/claude/.claude/settings.json"
with open(settings_path) as f:
    settings = json.load(f)

settings.setdefault("mcpServers", {})["memory"] = {
    "command": "python3",
    "args": ["/usr/local/bin/memory_mcp_server.py"],
    "env": {"DATABASE_URL": os.environ["DATABASE_URL"]}
}

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
PYEOF
fi
```

#### k8s Secret（jg-jiahd repo）

```yaml
# secret.sops.yaml（加密前）
stringData:
  DATABASE_URL: "postgresql://linebot:password@postgres.default.svc/linebot"
```

#### k8s Deployment env

```yaml
env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: k8scc-secret
        key: DATABASE_URL
```

### 共用同一個 PostgreSQL

k8scc 的 MCP memory server 和 linebot agents 共用同一個 `knowledge` 表，
只差在 `agent_id`：

| agent_id | 說明 |
|----------|------|
| `customer_service` | 客服 Agent 的學習知識 |
| `trello_agent` | Trello 查詢 Agent |
| `claude_code` | k8scc 裡 Claude Code 的明確記憶 |

### 建議路線

| 優先 | 方案 | 工作量 | 效果 |
|------|------|--------|------|
| 先做 | PVC 掛載 | 低（只改 k8s manifest） | auto-memory 不再遺失 |
| 後做 | MCP Server | 中（Dockerfile + script + k8s Secret） | 可明確呼叫 remember/recall |

---

---

## 已知技術坑（供未來參考）

| 問題 | 解法 |
|------|------|
| MQTT callback 內 `event.wait()` 阻塞 loop → Trello timeout | `_on_message` 開 `threading.Thread(daemon=True)` 背景處理 |
| MQTT request/reply race：reply 比訂閱先到 | 啟動時訂閱 wildcard `agents/trello/responses/#`，用 request_id routing `_pending` dict |
| paho-mqtt v2 rc=7 斷線迴圈 | 建構子加 `mqtt.CallbackAPIVersion.VERSION1`，加 `reconnect_delay_set`，`loop_forever(retry_first_connection=True)` |
| Anthropic SDK `response.content` 含 TextBlock，不可 JSON serialize | `[b.model_dump() for b in response.content]` |
| `TRELLO_TOKEN` 環境變數名稱不一致 | secret.yaml 用 `TRELLO_TOKEN`（非 `TRELLO_API_TOKEN`） |

## 待辦

- `deploy.yaml` 兩個 agent container 加 `securityContext`（restricted PodSecurity）
- NotifyAgent：整合 `trello_line_notifier.py` CronJob 邏輯進 MQTT 架構
- Phase 5：pgvector 語意搜尋（視需求）

*設計版本：2026-05-04*
*基於對話討論整理，持續修正中*
