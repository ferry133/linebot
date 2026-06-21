## Why

兩個問題一起解（同一條推播路徑、同一本額度帳）：

1. **額度爆量**：每日 3 批次 ＋ 廠商標記後對每位主管即時各推確認卡，LINE 200 則/月很快用罄。
2. **確認卡無法定位**：「待主管確認」卡只有 label 與標記人，缺**專案/卡片名稱**，主管找不到 to-do。

對策：**三批次合併為每日一次**；**主動 push 只送廠商（vendor）**；主管與客戶改由 **Rich Menu 拉取（走 Reply API，免費、不計額度）**取得各自的每日內容；確認卡改在主管的每日（拉取）內容中以**可操作且含定位**呈現；取消廠商標記的即時推播；空內容不 push。

> 註：目錄名沿用 `supervisor-confirm-card-context`，實際範圍已擴及「批次合併＋額度節省＋on-demand 拉取」。

## What Changes

- **三批次 → 每日一次**：單一每日批次評估全部觸發條件（#1–#9），每位收件人一則整合 Flex carousel。移除 noon、evening。
- **主動 push 僅送 vendor**：每日主動 push 只送 role=vendor 的收件人；**主管(admin/employee) 與客戶(customer) 不再被 push**。
- **Rich Menu on-demand 拉取（免費）**：常駐「📋 今日提醒」按鈕，使用者點按 → customer-service agent 以 **Reply API** 回覆其角色對應的每日內容（無 reply token 才 fallback push）。主管、客戶靠此取得每日內容。
- **取消即時推播**：廠商標記後 MUST NOT 即時推主管；仍**立即 Trello 暫定生效**＋建 pending＋回覆廠商。
- **可操作確認卡含定位**：主管的每日（拉取）內容中，每筆 pending 為一張帶「✅ 確認 / ↩︎ 退回」(夾帶 `cid`) 的卡片，含**專案名稱＋卡片名稱＋label＋標記人**。
- **空內容不 push**：vendor 該日無內容 → 不 push。（拉取則一律回覆，無內容回「今日無提醒」。）
- **資料**：`task_confirmations` 新增 `card_name` 快照，供渲染免逐筆回打 Trello。

## Capabilities

### New Capabilities
- `consolidated-daily-notification`: 三批次合併為單一每日批次評估 #1–#9、每人一則整合 carousel、**主動 push 僅送 vendor**、空內容不 push。
- `daily-notice-on-demand`: Rich Menu「今日提醒」按鈕 → postback → agent 以 Reply API 回覆該使用者角色對應的每日內容（免費；無 token 才 fallback push）。

### Modified Capabilities
- `trello-task-status-update`: 取消即時推播；pending 改由主管的每日（拉取）內容呈現；`task_confirmations` 新增 `card_name`。
- `notification-daily-summary`: 「待主管確認」升級為**可操作、含專案/卡片定位**的確認卡，於主管的每日（拉取）內容中呈現。

## Impact

- `trello_line_notifier.py`：合併三模式為單一每日批次；主動 push 過濾為 role=vendor；空內容不送；提供共用的「某使用者今日內容」組裝供 on-demand 重用。
- `agents/customer_service.py`：移除廠商標記時即時 `_notify_supervisors` 推播；`_insert_pending` 多存 `card_name`；新增 `o=daily` postback handler（組裝該使用者每日內容、含主管確認卡，經 reply 回覆）；`_handle_confirmation` 不變。
- LINE Rich Menu：建立含「今日提醒」的預設 rich menu（postback `o=daily`）。
- `migrations/`：新增 `012_task_confirmation_card_name.sql`；`shared/db.py` MIGRATIONS 追加。
- 交付沿用既有 `line-message-delivery`（reply 優先、push fallback），不另改其 spec。
- **jg-base 部署**：trello-notifier 三 CronJob 收斂為一；notifier 與 customer-service-agent image 一併 bump（多檔釘 sha 同步）。
