# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

「意念情境室內裝修」LINE 客服 Robot + 工程通知系統。

兩大功能：
1. **客服 Bot**（雙向）：客戶/廠商/主管透過 LINE 詢問 → Claude 理解並查 Trello → 即時回覆（優先走免費 Reply API）；無法回答時升級管理群組。
2. **每日工程通知**（單向）：單一每日 CronJob 掃描 Trello，依九項觸發條件（#1–#9）產出提醒。**主動 push 僅送廠商（vendor）**；主管/客戶改由 Rich Menu「今日提醒」on-demand 拉取（reply＝免費）。

> 架構已從早期單體 `linebot_server.py` 演進為 **MQTT 多 agent**。`linebot_server.py` 為 legacy，**已不部署**。行為規格以 `openspec/specs/` 為準。

## Commands

```bash
# 安裝依賴（與 Dockerfile 一致）
pip3 install requests flask anthropic psycopg2-binary "paho-mqtt>=2.0" pyyaml pillow pillow-heif authlib==1.9.1

# 各 workload（同一 image，不同進入點；本機需設好環境變數）
python3 gateway/line_gateway.py        # Flask Webhook + Reply/Push 出口
python3 agents/customer_service.py     # 客服 agent（Claude 五步循環）
python3 agents/trello_agent.py         # Trello 查詢 agent（掃描+快取+owner 過濾）
python3 agents/admin_server.py         # 管理 API（/api/*）+ 啟動時 run_migrations()

# 每日通知（合併批次，取代舊 morning/noon/evening）
python3 trello_line_notifier.py daily  # noon/evening 為相容 no-op；test 發測試訊息

# Rich Menu（一次性；需 LINE_CHANNEL_ACCESS_TOKEN，容器內含 fonts-noto-cjk 可畫中文）
python3 gateway/setup_richmenu.py --replace
```

## Architecture

```
客戶/廠商/主管 LINE → POST /webhook
        ↓
gateway/line_gateway.py (Flask)
  ├─ 驗簽 (HMAC-SHA256)；postback 解析 o=...
  ├─ 自動 upsert line_users（建檔）
  ├─ publish → MQTT agents/customer_service/inbox（夾帶 reply_token）
  └─ 訂閱 gateway/outbox → 出口：有 reply_token 先用 Reply API（免費），失敗才 Push API

agents/customer_service.py（獨立 process，五步循環 Perceive→Recall→Reason→Act→Reflect）
  ├─ 文字訊息 → Claude agentic loop（model claude-haiku-4-5-20251001, MAX_TOOL_TURNS=5）
  │    ⚠️ 目前以 `CHAT_ENABLED`（預設 false）**停用**；關閉時一般文字**靜默不回覆**
  │    （不呼叫 Claude/不查 Trello/不寫記憶）+ 原文轉發 LINE_NOTIFY_GROUP_ID
  │    （來源即該群時不轉，避免回音）；關鍵字與 postback 入口照常
  │    tools: query_trello / get_project_photos / escalate_to_manager
  ├─ postback：o=complete|incomplete（標記工項）/ o=confirm|reject（主管追認）
  │            / o=guide（線上說明）/ o=daily（今日提醒 → 每日 Flex）
  ├─ 關鍵字備援：GUIDE_KEYWORDS → 說明；DAILY_KEYWORDS → 今日提醒（同 o=daily Flex）
  └─ query_trello 委託 → MQTT agents/trello/requests（帶 allowed_board_ids + owner_alias）

agents/trello_agent.py：掃描 Trello（60s 快取，可被 invalidate）、依 allowed_board_ids（板層）
  與 owner_alias（廠商 owner 層）過濾後回覆
agents/trello_board_sync.py：每日同步看板名稱 → trello_boards 表（CronJob 0 19 * * *）

CronJob trello-notifier-daily（08:00 Asia/Taipei，週日至週五 0-5）
  → trello_line_notifier.py daily
       ├─ run_checks()：一次評估 #1–#9（合併原三批次；#6 逾期所有執行日皆呈現）
       ├─ build_daily_messages_for_user()：共用內容引擎（push 與 on-demand 拉取共用）
       ├─ 主動 push 僅送 role=vendor；空內容不送（skip-empty）
       └─ 主管摘要 + 可操作「待主管確認」卡（專案+卡片+label+確認/退回）僅於主管拉取時呈現
```

同一個 Docker image，執行模式由 k8s workload 的 `command` 指定。

## Key Files

| 檔案 | 說明 |
|------|------|
| `gateway/line_gateway.py` | Flask Webhook；Reply 優先/Push fallback 出口；postback 解析 |
| `gateway/setup_richmenu.py` | 一次性建立 Rich Menu（左 `o=daily` 今日提醒、右 `o=guide` 使用說明）|
| `agents/customer_service.py` | 客服 agent：Claude 五步循環、postback/keyword 路由、RBAC、確認流程 |
| `agents/trello_agent.py` | Trello 查詢 agent：掃描+快取+板層/owner 過濾 |
| `agents/trello_board_sync.py` | 每日同步看板名稱到 DB |
| `agents/admin_server.py` | 管理 API + 啟動跑 `run_migrations()` |
| `trello_line_notifier.py` | 每日通知 + 共用 Trello 函式/內容引擎（被 agents import）|
| `shared/db.py` | DB pool + migrations 清單 |
| `shared/broker.py` `shared/guide.py` | MQTT client；線上說明內容 |
| `gantt_generator.py` | 從 Trello 產生甘特圖 CSV |
| `linebot_server.py` | **legacy 單體，已不部署** |
| `openspec/specs/` | 行為規格（真實來源）；變更走 `/opsx:propose` |

## Notification & Visibility Model（重要）

- **三批次→單一每日批次**：每日一次（08:00 Sun–Fri）評估 #1–#9，每人一則整合 Flex carousel。
- **主動 push 僅 vendor**；admin/employee/customer 不被 push。
- **On-demand 拉取**：Rich Menu「今日提醒」(`o=daily`) 或輸入 DAILY_KEYWORDS → 經 **Reply API（免費）** 回該使用者角色對應內容。
- **每看板單一卡片**：主管的每看板把「工項提醒(#1–#8) + 摘要(其餘進行中)」合併為**一張** bubble（上段急迫含按鈕、下段其餘去重）；不再有獨立「每日工程摘要」bubble。`build_flex` 以 `_scan_boards()` **並行批次掃描 + 45s TTL 快取**（今日提醒 ~20s→~2s，warm ~0s；寫入後 `invalidate_scan_cache()` 失效）。
- **去 PII 專案標籤**：LINE 一律顯示 `public_label = {site_name}-{project_type}`（不含屋主名）；不回退 Trello 看板原名。屋主名只在 Trello/admin UI。
- **「✅完成」按鈕只給 vendor/customer**（不能碰 Trello 者）；admin/employee **不顯示**，改用 Trello 標記（`build_flex(show_buttons=)` 依角色）。
- **完成 / 核可流程**：
  - 廠商/客戶點 ✅完成 → **暫定生效** + 建 `task_confirmations` pending（含 card_name 快照）；**不即時推主管**。
  - 主管於每日內容看「待主管確認」卡按 **確認/退回**（`_handle_confirmation`）追認或還原廠商的暫定變更。
  - 主管自己標記工項 → 用 Trello（LINE 無完成鈕）。（早期的「主管完成二次確認(方案3)」已移除。）
- 詳見 specs：`consolidated-daily-notification`、`daily-notice-on-demand`、`notification-daily-summary`、`trello-task-status-update`、`project-public-label`。

## RBAC（角色與可見性）

| Role | 可見範圍 |
|------|---------|
| admin / employee | 所有專案（無限制）|
| vendor | **僅自己被 `[@(alias)]` 標記的工項**（tag 為唯一依據，與板層指派無關）|
| customer | 僅其 `line_user_projects` 指定看板（整看板，屋主看全貌）|
| visitor | 無 |

- 對話查詢：customer-service 帶 `allowed_board_ids`（vendor=None、customer=board 清單）+ `owner_alias`（vendor=自身 alias）給 trello-agent。
- 權限一律從 `line_user_projects` JOIN `projects` 查，**不得**用 `line_users.projects` JSONB。
- 角色/指派變更會清 `working_memory`（避免 Claude 從舊對話繞過 RBAC）。詳見 spec `role-based-access-control`。

## Environment Variables

| 變數 | 用途 |
|------|------|
| `ANTHROPIC_API_KEY` | Claude API 金鑰 |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API（push/reply/richmenu/profile）|
| `LINE_CHANNEL_SECRET` | Webhook 驗簽 |
| `LINE_NOTIFY_GROUP_ID` | escalate 升級通知群組（未設定 fallback sa/larry）|
| `TRELLO_API_KEY` / `TRELLO_TOKEN` | Trello API 憑證 |
| `DATABASE_URL` | linebot 專屬 PostgreSQL（與 k8scc 分開）|
| `CHAT_ENABLED` | 客服自由對話開關；**預設 false（停用）**。恢復：jg-extras `linebot/app/deploy.yaml` 設 `"true"` + rollout。非 `1/true/yes/on` 一律視為關閉（fail-closed）；pod 啟動 log 會印 `chat=enabled|disabled` |
| `AUTH0_DOMAIN` / `AUTH0_CLIENT_ID` / `AUTH0_CLIENT_SECRET` | admin UI 的 Auth0 登入（linebot 專用 Regular Web App；callback `https://linebot-admin.jiahd.cc/callback`）|
| `ADMIN_SESSION_SECRET` | admin session cookie 簽章；**未設定則 admin server 拒絕啟動** |
| `ADMIN_ALLOWED_EMAILS` | admin UI 登入白名單（逗號分隔）；**空＝無人可登入（fail-closed）**。Auth0 只證明身分，這份名單才是閘門。值是明文，住在 jg-extras `kubernetes/apps/extras/default/linebot/app/admin.yaml` 的 `env`（不在 secret）；改動走 jg-extras PR（見「k8s 部署」），Flux 套用即滾動重啟 admin。比對只轉小寫、**不正規化 Gmail 的點**（`jiahd.oper@` ≠ `jiahdoper@`）。目前：jiahdadm、ferry133、jiahd.oper（2026-10-21 加，當時在 jg-base `ea198df`；jg-extras `70a5dca`）|

## Agent Memory DB

linebot agents 用**獨立 PostgreSQL**，以 `agent_id` 隔離（`customer_service`、`trello_agent`）。
Schema（`migrations/`，目前到 `012_task_confirmation_card_name.sql`）：
- `knowledge`（語意）、`episodes`（情節）、`working_memory`（工作）
- `line_users` / `projects` / `line_user_projects` / `trello_boards` / `sites` / `task_confirmations`
- migrations 由 `agents/admin_server.py` 啟動時 `run_migrations()` 自動套用。

## k8s 部署（jg-extras）

manifests 在 **`ferry133/jg-extras`**（private；2026-10 由 jg-base 拆出，**擁有者是 jg-base agent**）：
`kubernetes/apps/extras/default/linebot/`（gateway/agents/admin Deployment，及 `deploy.yaml` 內的 `trello-board-sync` CronJob）
與 `.../trello-notifier/`（`trello-notifier-daily` CronJob）。jg-base 已不含 linebot。叢集為 **jg-jiahd**
（kubeconfig：`jg-jiahd/kubeconfig-sa`；linebot namespace；admin 8081）。

**Release/部署流程**：
1. 改 linebot 程式碼 → PR → merge `main` → CI（`.github/workflows/build.yaml`）build `ghcr.io/ferry133/linebot:<git-short-sha>`。
2. jg-extras：`scripts/bump-linebot-image.sh <sha>`（一次改 `linebot/app/deploy.yaml`×4、`admin.yaml`、`trello-notifier/app/cronjobs.yaml`，共 6 處）。
3. **開 jg-extras PR 附量測，等 ferry133 本人說「合併 X」才合**；peer 轉述的同意不算。只有 ferry133 直接指示推送時才直推 `main`，並在 commit 訊息寫明誰推、依誰指示（例：`02458b8`）。CI 在 PR 與 push main 都會跑。
4. `flux --kubeconfig ./kubeconfig-sa reconcile source git jg-extras -n flux-system`，等 Kustomization **`linebot`**（不是 `extras-linebot`）到新 revision 且 Ready，再對 4 個 Deployment 跑 `rollout status`、看**新 pod** 的 log（滾動期間 `logs deploy/X` 會挑到舊 pod）。
5. 若改了 Rich Menu，部署後跑一次 `setup_richmenu.py --replace`。

⚠️ **image sha 釘在 jg-extras 多檔，務必一起改**（用 bump script），否則部分 workload 跑舊 image →
症狀如「通知 0 收件人 / 行為不一致」。（舊的 `migrate-contacts-job.yaml` 已於 jg-extras#12 移除，bump script 不再需要跳過任何檔。）

- **LINE Developer Console**：Webhook URL `https://<domain>/webhook`，啟用 webhook。

## Trello 標記格式

「工項」才觸發通知與可見性邏輯（alias 對應 `line_users.alias_name`）。工項有兩種寫法，定義見 spec `work-item-tag`，程式入口是 `work_item_of_card` / `work_item_of_checkitem`，所有讀取點都走這兩個函式。

**1. 文字標記**：寫在卡片描述第一行或待辦項名稱的開頭。

```
[@(曾宇晟),20260501-20260530:1800] 拆除舊有磁磚
[@(Larry)@(SA),-20260530] 防水層施工驗收
```

**2. Trello 原生日期**（2026-10 起）：

| | 負責人 | 日期 |
|---|---|---|
| 卡片 | 名稱中的 `@(代號)`，例如 `108.[人造石@(石凱)] 施工`，稱為**卡片負責人** | 卡片的開始日與到期日 |
| 待辦項（不必寫標記） | 指派成員是**公司帳號**（Trello token 擁有者 `jiahdoper`）時歸「公司」，提醒管理者與員工；否則為卡片負責人；兩者皆無則不算工項 | 只有到期日（Trello 待辦項沒有開始日），**沒有到期日的不追蹤** |

- 卡片同時有兩種寫法時，**以原生寫法為準**，描述標記會被忽略。
- 待辦項是文字標記時，照文字解析，不看到期日與指派成員。
- 卡片名稱有 `@(代號)` 卻沒設日期，屬於錯誤設定：卡片本身不算工項，並列入主管每日摘要的警告「⚠️ 卡片已指定負責人但未設日期」。
- 工期表 `gantt_sheets_sync.gs`（Apps Script）以 JS 實作同一套規則，**改規則時兩邊都要改**；修改後要手動貼回 Apps Script。測試：`node tests/smoke_gantt_sheets_sync.js`、`python3 tests/smoke_work_item_tag.py`。

`chatBarText` 等 LINE 限制：Rich Menu chatBarText ≤ 14 字元。
