## 1. Trello 寫入層（trello_line_notifier.py）

- [ ] 1.1 新增 `set_checkitem_state(card_id, checkitem_id, complete: bool)` → `PUT /1/cards/{cardId}/checkItem/{itemId}`，`state=complete|incomplete`；回傳 (status_code, ok)。
- [ ] 1.2 新增 `set_card_due_complete(card_id, complete: bool)` → `PUT /1/cards/{cardId}`，`dueComplete=true|false`；回傳 (status_code, ok)。

## 2. 提醒卡片按鈕（trello_line_notifier.py build_flex）

- [ ] 2.1 #1–#8 每則工項 rec 帶上 `board_id`/`card_id`/`checkItem_id`/`source`（run_checks 收集 notifications 時補帶）。
- [ ] 2.2 `build_flex` 在每則工項 footer 加「✅ 標記完成 / ↩︎ 取消完成」`action: postback`，`data` 編碼 `op,b,c,i,s`（≤300 字元）。

## 3. Gateway postback（gateway/line_gateway.py）

- [ ] 3.1 webhook 處理 `postback` event：解析 `data`，發布到 customer-service inbox，payload `kind="status_update"` + 解析欄位 + user_id。

## 4. customer-service 寫入流程（agents/customer_service.py）

- [ ] 4.1 `_on_message` 依 `kind`：`status_update` → `_handle_status_update(...)`（不進 Claude loop）。
- [ ] 4.2 `_handle_status_update`：驗 owner/supervisor（解析該工項 tag owner 比對 user alias；或 role∈admin/employee），否則婉拒。
- [ ] 4.3 通過後經 MQTT 送 `op="update"` 請求（帶 ids + 目標狀態）給 trello-agent，等待回覆並回 LINE。

## 5. trello-agent mutation（agents/trello_agent.py）

- [ ] 5.1 `_on_request` 依 `op`（預設 query）分派；新增 `_update(...)`。
- [ ] 5.2 `_update`：依 card/checkItem id 讀卡、重驗 owner + `allowed_board_ids`；冪等檢查；依 source 呼叫 1.1/1.2 寫入；寫入後清掃描 cache；結構化回報成功/失敗（非 2xx 如實回報）。

## 6. 驗證

- [ ] 6.1 `ast.parse` 四檔通過。
- [ ] 6.2 pod 內測試卡片：owner 按「完成」→ checklist state / card dueComplete 確實變更；按「取消」還原。
- [ ] 6.3 非 owner（且非 admin/employee）→ 被拒不寫入；偽造 postback 指向越權看板 → 被擋。
- [ ] 6.4 寫入後立即查詢反映新狀態（cache 已失效）；冪等不重寫；Trello 非 2xx 如實回報。

## 7. 上線

- [ ] 7.1 commit + push linebot；CI build。
- [ ] 7.2 bump jg-base 全部 image pin → Flux reconcile。
