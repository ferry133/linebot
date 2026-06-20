## 1. DB migration

- [x] 1.1 新增 `migrations/011_task_confirmations.sql`（pending/confirmed/rejected 追認紀錄，index on status）+ 註冊於 `shared/db.py` MIGRATIONS。

## 2. Trello 寫入層（trello_line_notifier.py）

- [x] 2.1 `set_checkitem_state(card_id, checkitem_id, complete)` → PUT checkItem state。
- [x] 2.2 `set_card_due_complete(card_id, complete)` → PUT card dueComplete。
- [x] 2.3 `add_card_comment(card_id, text)` → POST 卡片留言（稽核）；另加 `get_card` 供 owner 重驗。

## 3. 提醒卡片按鈕（trello_line_notifier.py）

- [x] 3.1 check_item rec 擴為 9-tuple 帶 `board_id/card_id/checkItem_id/source`（#7/#8 rec 補 None）。
- [x] 3.2 `build_flex` 每則工項加「✅ 標記完成 / ↩︎ 取消完成」postback（`_status_buttons`/`_postback_data`，≤300）。
- [x] 3.3 #9 摘要加「⏳ 待主管確認」清單（`_pending_confirmations` 查 pending）；摘要本就只發 supervisor。

## 4. Gateway postback（gateway/line_gateway.py）

- [x] 4.1 `webhook` 處理 `postback` event：`_parse_postback` 解析 `data` → inbox `kind="postback"` + 解析欄位 + user_id + reply_token。

## 5. customer-service 寫入/追認（agents/customer_service.py）

- [x] 5.1 `_on_message` 依 `kind="postback"` → `_process_postback`（不進 Claude loop）。
- [x] 5.2 `_handle_status_update`：`get_card` 重讀 + `_resolve_target` 解析 owner/label/現況；驗 owner(alias∈tag)/supervisor + 看板授權；冪等；直接呼叫寫入層寫 Trello；稽核留言；publish invalidate。
- [x] 5.3 supervisor 直接標記 → 定案；廠商 → `_insert_pending` + `_notify_supervisors`（confirm/reject Flex 按鈕）。
- [x] 5.4 `_handle_confirmation`：限 admin/employee；confirm → `_resolve_pending(confirmed)` + 留言；reject → 直接還原 Trello + `_resolve_pending(rejected)` + 留言 + invalidate；已處理冪等。

## 6. trello-agent cache 失效（agents/trello_agent.py）

- [x] 6.1 訂閱 `agents/trello/invalidate`，`_on_invalidate` 清掉掃描 `_cache`（取代原 mutation handler 設計——見 design D1 修正）。

## 7. 本機驗證

- [x] 7.1 五檔 `ast.parse` 通過；stub 匯入 customer_service/trello_agent 各方法存在；`_parse_postback` 與 postback data（105 字元 ≤300）驗證通過。

## 8. 部署後 pod 驗證

- [ ] 8.1 廠商按完成 → Trello 立即生效 + pending row + supervisor 收到確認/退回通知；稽核留言出現。
- [ ] 8.2 supervisor 確認 → row=confirmed、Trello 不變；退回 → Trello 還原 + row=rejected。
- [ ] 8.3 supervisor 直接標記 → 免 pending；非 owner/非 supervisor 被拒；越權 postback 被擋；confirm/reject 冪等。
- [ ] 8.4 #9 摘要對 supervisor 顯示待確認清單。

## 9. 上線

- [ ] 9.1 commit + push linebot；CI build。
- [ ] 9.2 bump jg-base 全部 image pin → Flux reconcile（migration 011 由各 workload 啟動時 `run_migrations` 自動套用）。
