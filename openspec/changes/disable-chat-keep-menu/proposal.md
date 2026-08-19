## Why

客服 agent 的自由對話（Claude agentic loop）目前對每則文字訊息都會呼叫 Claude API 並可能連帶查 Trello／升級主管，成本與回覆品質皆不穩定；營運上希望**暫時**停用對話，只留下三個可預期、零 LLM 成本的功能入口（今日提醒／未來工項／使用說明）。停用必須是可逆的開關，而非刪除程式碼。

## What Changes

- 新增對話功能開關（環境變數 `CHAT_ENABLED`，預設 **關閉**）。關閉時 customer-service agent 對一般文字訊息**不呼叫 Claude**、不查 Trello、不 escalate、不寫入 `working_memory`／`episodes`／`knowledge`。
- 關閉期間收到未命中保留入口的文字訊息 → 以固定引導訊息經 **Reply API（免費）** 回覆（告知已轉交專人並指引 Rich Menu 三格）。
- 同時把**原文轉發主管**（`LINE_NOTIFY_GROUP_ID`；未設定則送 `line_users` 的 admin，無 admin 才退 employee），附來源身分/角色/時間，讓停用期間的提問不會沉沒；來源本身是該通知群時不轉發（避免回音）。
- **順帶修掉既有靜默失敗**：`_escalate` 原本回退 `contacts` 的 `sa`/`larry`，但 contacts 以顯示名為 key → 永遠落空；production `LINE_NOTIFY_GROUP_ID` 為空，因此升級通知一直沒人收到卻 log「已通知」。改用同一個以 role 為準的出口，並回報實際送達數。
- **保留不受開關影響**：
  - Rich Menu postback `o=daily`／`o=someday`／`o=future`／`o=guide`
  - 文字關鍵字備援：`GUIDE_KEYWORDS`（使用說明）、`DAILY_KEYWORDS`（今日提醒）、未來/過去工項關鍵字
  - 工項狀態 postback `o=complete`／`o=incomplete` 與主管追認 `o=confirm`／`o=reject`
  - 每日 CronJob 主動推播（vendor-only）與所有 RBAC 過濾
- 開關開啟（`CHAT_ENABLED=true`）時行為與現況完全相同，無需再次改動程式碼。

## Capabilities

### New Capabilities
- `conversation-mode-toggle`: 客服對話（Claude agentic loop）的可逆開關語意——關閉時的回覆行為、關閉時仍必須運作的入口清單、以及關閉時禁止產生的副作用（LLM 呼叫、記憶寫入、escalate）。

### Modified Capabilities
- `agent-identity-grounding`: 其身分注入與 episode 品質評分要求，改為**僅在對話功能啟用時**適用；關閉時不進入該流程也不寫入記憶。

## Impact

- 程式碼：`agents/customer_service.py`（`_on_message` 路由、轉發出口 `_notify_managers`／`_forward_offline_message`）、`gateway/line_gateway.py`（inbox payload 增 `group_id`，供去回音判斷）。`trello_line_notifier.py`、`agents/trello_agent.py` 不變。
- 部署：`jg-base` 的 `kubernetes/apps/extras/default/linebot/app/deploy.yaml` 需在恢復對話時加上 `CHAT_ENABLED=true`；本次關閉僅需 bump image（預設即關閉）。
- 成本：關閉期間 Anthropic API 用量降為 0（每日通知本身不呼叫 Claude）。
- 風險：客戶以文字提問不再獲得 AI 實質回答，改由固定引導訊息 + 主管人工回覆承接；主管通知群將收到停用期間的每則來訊（量大時為噪音）。
