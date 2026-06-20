## Why

目前 trello-agent 只能**讀**。工項的負責廠商（被 tag 在 `[@(who),…]` 的 owner）在 LINE 收到工程提醒後，想直接標記該項完成時，customer-service agent 只能拒絕並請對方自己去 Trello 操作（見實際對話：「⚠️ 我無法直接在 Trello 上標記工項完成」）。應讓**工項 owner 透過 LINE UI**（提醒卡片上的按鈕）代為更新 Trello 完成狀態，省去登入看板。

## What Changes

- **目標選定（LINE UI / postback）**：每則 #1–#8 提醒（本就只發給該工項 owner）的 Flex 卡片新增「✅ 標記完成 / ↩︎ 取消完成」按鈕，postback `data` 夾帶精確 `board_id + card_id + checkItem_id + source`。owner 一按即精準命中該工項，零模糊。
- **Gateway 處理 postback**：`line_gateway.py` 新增 postback event 處理，轉交 customer-service agent（與文字訊息同一條 inbox，payload 標明為 status-update 動作）。
- **寫入路徑**：trello-agent 依 postback 帶的 id 直接寫入：
  - checklist 工項 → `checkItem.state = complete|incomplete`
  - card 層級工項（card desc tag）→ `card.dueComplete = true|false`
  - **不移動卡片欄位**（不搬「已完成」欄）。
- **授權（owner + 管理者/員工）**：可標記的人是該工項 tag 的 owner——按鈕操作者的 `line_users.alias_name` 須出現在該工項 `[@(who)…]` 的 names 內；`role ∈ (admin, employee)` 視為 supervisor 亦放行。兩者皆非則一律拒絕。
- **追認流程（先生效 + 事後追認）**：
  - **廠商**（owner 但非 supervisor）按完成/取消 → Trello **立即生效**（暫定），並在 DB `task_confirmations` 記一筆 `status=pending`，同時推播給 supervisor（admin/employee）一則含「✅ 確認 / ❌ 退回」按鈕的通知。
  - **supervisor 事後追認**：按「確認」→ 該筆 `status=confirmed`（定案，Trello 不變）；按「退回」→ `status=rejected` 並將 Trello **還原**（complete↔incomplete 反向），留言記錄。
  - **supervisor 自己直接標記** → 立即定案，**免追認**（不產生 pending）。
  - 待確認期間 Trello 已是新狀態（通知系統不再催）；**每日摘要（#9）對 supervisor 加列「待確認」清單**，避免暫定狀態被遺忘。
- **稽核留言（who/when/what）**：每次寫入（廠商暫定、supervisor 確認/退回）皆於該卡片「留言與活動」留言，記錄**操作者**（LINE 顯示名／alias）、**時間**（台北）、**動作**與工項，供追溯。
- 回報：寫入成功/失敗如實回覆；Trello 回非 2xx 不謊報成功。

## Capabilities

### New Capabilities

- `trello-task-status-update`: 定義工項 owner（及 supervisor）透過 LINE 提醒卡片按鈕（postback）更新 Trello 工項完成狀態的行為、owner 授權、稽核留言，以及**廠商暫定 + supervisor 事後追認/退回**的審核流程與待確認呈現。

### Modified Capabilities

- `notification-daily-summary`: 每日摘要對 supervisor（admin/employee）新增「待主管確認」清單，列出尚未追認的廠商暫定變更。

## Impact

- 程式：
  - `trello_line_notifier.py`：#1–#8 提醒 Flex 卡片加「完成/取消」postback 按鈕（夾帶 board_id/card_id/checkItem_id/source）；新增 Trello 寫入 helper（`set_checkitem_state`、`set_card_due_complete`、`add_card_comment`）；#9 摘要對 supervisor 加「待確認」清單。
  - `gateway/line_gateway.py`：新增 postback event 處理（status-update 與 confirm/reject 兩類）→ 發布到 customer-service inbox。
  - `agents/customer_service.py`：處理 postback 動作 → owner/supervisor 驗證 → 廠商暫定寫入並建立 pending、推播 supervisor；supervisor confirm/reject 解析 pending 並定案/還原。
  - `agents/trello_agent.py`：mutation handler 依 postback id 定位並寫入（owner 與看板授權再驗一次）、寫稽核留言。
- DB：新增 migration `011_task_confirmations.sql`（pending/confirmed/rejected 追認紀錄）。
- 行為：廠商可一鍵標記、主管事後追認；暫定狀態以每日摘要待確認清單防遺忘。Trello token 需寫入權限（現有即可）。postback `data` ≤ 300 字元，必要時改短 token。
