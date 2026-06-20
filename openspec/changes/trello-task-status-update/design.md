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
- 廠商變更為暫定，supervisor 事後追認/退回；待確認清單防遺忘。

**Non-Goals:**
- 不移動卡片欄位（不搬「已完成」欄）。
- 不新增/刪除卡片或 checklist、不改日期或標記文字。
- 非 owner / 非 supervisor 不可寫入。
- 不做純文字模糊比對的寫入（改用按鈕 postback）。
- 不對追認設逾時自動定案/自動退回（事後追認無期限；僅以待確認清單提示）。

## Decisions

**D1（實作修正）：寫入由 customer-service 直接執行；trello-agent 僅失效掃描 cache。**
原設計擬把寫入也走 MQTT 委派給 trello-agent。實作時發現：customer-service 本就 import 共用 Trello 層（`trello_line_notifier`），owner 驗證需要直接 `get_card` 讀卡，寫入是單純 PUT，無 trello-agent 掃描 cache 的效益；多一段 MQTT round-trip 只增延遲與複雜度。
→ 改為 customer-service 直接呼叫 `set_checkitem_state` / `set_card_due_complete` / `add_card_comment` + `get_card`/`parse_tag` 做 owner 驗證；寫入後 publish 一則輕量訊息到 `agents/trello/invalidate`，trello-agent 訂閱後清掉 `_cache`（滿足「寫入後狀態一致」）。
- trello-agent 因此**不需** mutation handler，只加一個 cache-invalidate 訂閱。

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

**D7：稽核留言寫進卡片「留言與活動」。**
寫入成功後，trello-agent 以 `add_card_comment(card_id, text)`（`POST /1/cards/{cardId}/actions/comments`）在該卡新增一則留言，內容含操作者、台北時間、動作與工項 label，例如：
`🤖 LINE：{操作者顯示名}（{alias}）於 2026/06/19 14:30 標記「{label}」為完成`。
- 操作者顯示名／alias 由 `line_users` 以 user_id 反查（display_name + alias_name）。
- 留言會掛在 API token 所屬的 Trello 帳號名下，但文字明確記錄真正的 LINE 操作者 → 可追溯 who/when/what。
- 留言失敗不影響狀態寫入結果（狀態已改成功即回報成功），但記 log。

**D8：追認狀態存 DB `task_confirmations`（非 Trello 標籤）。**
Trello 完成旗標是二元的，無法表達「暫定/待確認」。改用 linebot 自有 PostgreSQL 新表 `task_confirmations`，per-item 追蹤、可查詢供每日摘要列待確認清單。
```
task_confirmations(
  id, board_id, card_id, checkitem_id NULL, source,   -- 目標工項
  label, target_state,                                 -- 顯示與廠商claim的目標狀態
  claimer_user_id, claimer_alias, claimed_at,
  status,                                               -- pending|confirmed|rejected
  confirmer_user_id NULL, resolved_at NULL
)
```
- 替代（Trello 標籤「待確認」）：否決——card 層級、無法 per-checklist-item、且污染看板標籤。

**D9：廠商暫定 vs supervisor 直接定案。**
postback 進來時先判操作者：
- **supervisor（admin/employee）**：直接寫 Trello + 稽核留言，**不建 pending**（本身即權威）。
- **廠商（owner 非 supervisor）**：寫 Trello（暫定）+ 稽核留言（註明「待確認」）+ insert `task_confirmations` status=pending + 推播 supervisor 一則含確認/退回按鈕（postback `data` 帶 confirmation id）。

**D10：confirm/reject 為另一類 postback。**
supervisor 通知上的「✅ 確認 / ❌ 退回」按鈕 postback `data` 帶 `op=confirm|reject` 與 `cid=<confirmation id>`。gateway 同樣轉 inbox；customer-service：
- confirm → 該 row status=confirmed、resolved_at、confirmer；卡片留言「主管X 已確認」。Trello 不變。
- reject → status=rejected；**還原 Trello**（complete↔incomplete 反向，依 source 呼叫 1.1/1.2）；卡片留言「主管X 退回」。
- 僅 admin/employee 可按確認/退回；非 supervisor 點按一律拒絕。已 resolved 的 cid 再點 → 回覆已處理（冪等）。

**D11：每日摘要待確認清單。**
#9 morning 摘要對 supervisor 收件者，於既有警告區塊後新增「⏳ 待主管確認」清單（查 `task_confirmations` status=pending），列工項 label / 廠商 / claim 時間。非 supervisor 收件者不顯示。重用既有 warnings bubble 機制。

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
