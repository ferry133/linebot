## Context

讀取路徑現況：`customer_service._query_trello` → MQTT `agents/trello/requests`（payload 帶 `query_type`/`keyword`/`allowed_board_ids`/`project_map`）→ `trello_agent._on_request` → `_scan_all_items()`（60s cache）→ 文字結果 → reply topic。

授權現況：`_get_user_auth(user_id)` 依 `line_users.role` 回傳 `allowed_board_ids`（admin/employee=None 不限、vendor/customer=指派看板、visitor=[] 封鎖）。

掃描結果 `_scan_all_items()` 目前**未帶 Trello id**（只有 board/list/card 名稱與 label），寫入需要 `card_id`、checklist 的 `checkitem_id`，以及 `source`（card_desc / checklist）以決定寫 `dueComplete` 還是 `checkItem.state`。

完成定義沿用既有 completion gate：card 用 `dueComplete`，checklist 用 `state == "complete"`。

## Goals / Non-Goals

**Goals:**
- 工項 owner（被 tag 的廠商）透過 LINE 提醒卡片按鈕一鍵標記完成/取消。
- 授權＝工項 owner（tag alias 比對）或 admin/employee supervisor。
- postback 帶精確 id，無關鍵字模糊；重用既有 MQTT request/reply。

**Non-Goals:**
- 不移動卡片欄位（不搬「已完成」欄）。
- 不新增/刪除卡片或 checklist、不改日期或標記文字。
- 非 owner / 非 supervisor 不可寫入。
- 不做純文字模糊比對的寫入（改用按鈕 postback）。

## Decisions

**D1：寫入仍由 trello-agent 執行（集中 Trello 存取）。**
customer-service 不直接打 Trello，改送 MQTT mutation 請求給 trello-agent。沿用同一 request topic，payload 增 `op` 欄位（`"query"` 預設 / `"update"`）。`_on_request` 依 `op` 分派。
- 替代：另開 `agents/trello/mutations` topic——否決：多一個訂閱與 reply 對接，效益不大；`op` 欄位已足夠區隔。

**D2：目標選定用 LINE 提醒卡片按鈕（postback），精確 id 無模糊。**
#1–#8 提醒 Flex 卡片每則工項加「✅ 標記完成 / ↩︎ 取消完成」按鈕，`action: postback`，`data` 夾帶 `op=complete|incomplete`、`b=<board_id>`、`c=<card_id>`、`i=<checkItem_id 或空>`、`s=card|checklist`。owner 一按即定位該工項，不需關鍵字比對或消歧義。
- postback `data` ≤ 300 字元：Trello id 為 24 hex，三個 id + 旗標約 < 120 字元，足夠；必要時改存短 token 映射。
- 替代（純文字 + 消歧義）：否決——owner 受眾雖小但仍可能誤標；按鈕零模糊且最貼近「LINE UI」。

**D3：授權＝工項 owner（tag alias），supervisor 例外。**
按鈕操作者的 `line_users.alias_name` 須出現在該工項 `[@(who)…]` 的 names；或操作者 `role ∈ (admin, employee)`（supervisor）→ 放行。其餘拒絕。
- 雙閘：customer-service 端先驗 owner/supervisor；trello-agent 端再以 `allowed_board_ids` + 重新解析該卡 tag 的 owner 驗一次，避免偽造 postback 越權。
- owner 判定需要該工項的 tag names；trello-agent 依 postback 帶的 card/checkItem id 重新讀取該卡，解析 tag 取 names 比對操作者 alias。

**D6：Gateway 處理 postback event。**
`line_gateway.py` 現只處理 `message`。新增 `postback` event：解析 `data`，連同 user_id 發布到 customer-service inbox（payload `kind="status_update"` + 解析後欄位）。customer-service `_on_message` 依 `kind` 分派到寫入流程而非 Claude loop（postback 是結構化動作，不需 LLM）。

**D4：Trello 寫入 helper 放 `trello_line_notifier.py`（共用 Trello 層）。**
- `set_checkitem_state(card_id, checkitem_id, complete: bool)` → `PUT /1/cards/{cardId}/checkItem/{itemId}`，`state=complete|incomplete`。
- `set_card_due_complete(card_id, complete: bool)` → `PUT /1/cards/{cardId}`，`dueComplete=true|false`。
掃描 `_scan_all_items()` 補帶 `card_id`（card desc 與 checklist 皆有）、`checkitem_id`（checklist）。寫入後清掉 trello-agent 的掃描 cache，避免立即查詢回舊狀態。

**D5：system prompt 行為。**
告知對授權使用者可代為「標記完成/取消」，使用 `update_task_status`；定位不唯一時先請使用者確認；非授權使用者婉拒並引導。

## Risks / Trade-offs

- [誤標完成] → 唯一命中才寫 + 明確回報變更內容；多筆一律消歧義不動。
- [越權寫入] → 雙閘（role gate + board 過濾）。
- [cache 造成回報不一致] → 寫入後失效 trello-agent cache；回報以實際 API 回應為準。
- [Trello token 寫入權限] → 既有 token 具寫入；若被縮權，寫入回 4xx，agent 回報失敗（不假裝成功）。

## Migration Plan

純程式變更，無 DB／schema 變更。部署：push linebot → CI → bump jg-base 全部 pin → Flux reconcile。Rollback：還原 image pin（工具消失，行為回到唯讀）。
