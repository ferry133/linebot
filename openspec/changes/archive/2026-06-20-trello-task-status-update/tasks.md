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

- [x] 8.1 migration 011 已套用（task_confirmations 13 欄）；非破壞性驗證：`_resolve_target` 讀真實卡解析 owner/label/狀態、pending 生命週期(insert→load→_pending_confirmations→resolve confirmed=1→冪等 re-resolve=0→cleanup)、postback/confirm-reject flex 結構皆通過。
- [x] 8.2 pod 內真實 E2E（larryoffice=廠商、larry=主管、創世紀M3 card「20.保護進場」兩個 test 工項）：廠商標記完成→Trello 暫定生效+pending+稽核留言「待主管確認」；主管確認(定案,冪等)；主管直接標記(免追認,不建pending)；廠商標記→主管退回→Trello 還原+rejected；非owner婉拒零寫入；冪等不重寫；每次寫入 publish cache-invalidate。Trello 留言與活動 5 則稽核留言齊全（操作者+台北時間+動作+label）。板面復原乾淨。LINE-UI push 腿因免費版 200/月額度用罄暫緩，待額度重置/升級。

## 9. 上線

- [x] 9.1 commit + push linebot 131b0ac；CI green。
- [x] 9.2 bump jg-base 全部 9 pin → Flux reconcile（含修正 deploy.yaml 殘留 eaba805 skew）；migration 011 已自動套用。
