## Why

目前 trello-agent 只能**讀**。工項的負責廠商（被 tag 在 `[@(who),…]` 的 owner）在 LINE 收到工程提醒後，想直接標記該項完成時，customer-service agent 只能拒絕並請對方自己去 Trello 操作（見實際對話：「⚠️ 我無法直接在 Trello 上標記工項完成」）。應讓**工項 owner 透過 LINE UI**（提醒卡片上的按鈕）代為更新 Trello 完成狀態，省去登入看板。

## What Changes

- **目標選定（LINE UI / postback）**：每則 #1–#8 提醒（本就只發給該工項 owner）的 Flex 卡片新增「✅ 標記完成 / ↩︎ 取消完成」按鈕，postback `data` 夾帶精確 `board_id + card_id + checkItem_id + source`。owner 一按即精準命中該工項，零模糊。
- **Gateway 處理 postback**：`line_gateway.py` 新增 postback event 處理，轉交 customer-service agent（與文字訊息同一條 inbox，payload 標明為 status-update 動作）。
- **寫入路徑**：trello-agent 依 postback 帶的 id 直接寫入：
  - checklist 工項 → `checkItem.state = complete|incomplete`
  - card 層級工項（card desc tag）→ `card.dueComplete = true|false`
  - **不移動卡片欄位**（不搬「已完成」欄）。
- **授權（owner-based）**：可標記的人是該工項 tag 的 owner——按鈕操作者的 `line_users.alias_name` 須出現在該工項 `[@(who)…]` 的 names 內；admin／employee 視為 supervisor 亦放行。非 owner 一律拒絕。
- 回報：寫入成功/失敗如實回覆；Trello 回非 2xx 不謊報成功。

## Capabilities

### New Capabilities

- `trello-task-status-update`: 定義工項 owner（及 supervisor）透過 LINE 提醒卡片按鈕（postback）由 agent 代為更新 Trello 工項完成狀態（完成／取消）的行為、owner 授權邊界與目標定位。

### Modified Capabilities

（無——讀取查詢與 RBAC 既有行為不變；本變更新增獨立的寫入能力。提醒卡片新增按鈕屬既有 #1–#8 呈現的附加，不改觸發判斷。）

## Impact

- 程式：
  - `trello_line_notifier.py`：#1–#8 提醒 Flex 卡片加「完成/取消」postback 按鈕（夾帶 board_id/card_id/checkItem_id/source）；新增 Trello 寫入 helper（`set_checkitem_state`、`set_card_due_complete`）。
  - `gateway/line_gateway.py`：新增 postback event 處理 → 發布到 customer-service inbox（標明 status-update）。
  - `agents/customer_service.py`：inbox 處理 postback 動作 → owner 驗證 → MQTT 送寫入請求給 trello-agent → 回覆結果。
  - `agents/trello_agent.py`：新增 mutation handler，依 postback id 定位並寫入（owner 與看板授權再驗一次）。
- 行為：工項 owner 可在 LINE 一鍵標記完成/取消；非 owner 被拒。寫入對外、不可輕易復原 → 以精確 id + owner 驗證 + 如實回報降低誤動。
- 無 DB schema 變更。Trello token 需具寫入權限（現有 token 即可寫）。postback `data` 長度上限 300 字元，需精簡或用短 token。
