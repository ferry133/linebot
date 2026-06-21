## 1. 資料層：card_name 快照

- [x] 1.1 新增 `migrations/012_task_confirmation_card_name.sql`：`ALTER TABLE task_confirmations ADD COLUMN card_name TEXT`
- [x] 1.2 `shared/db.py` MIGRATIONS 清單追加 `012_task_confirmation_card_name.sql`
- [x] 1.3 `_insert_pending` 簽名與 INSERT 加 `card_name`；`_handle_status_update` claim 當下傳入 `card.get("name","")`

## 2. 取消即時推播（agent）

- [x] 2.1 `_handle_status_update` 廠商分支移除 `_notify_supervisors` 呼叫（仍寫 Trello 暫定＋建 pending＋回覆廠商）
- [x] 2.2 移除/停用 `_notify_supervisors`、`_confirm_flex`（確認卡建構移至共用內容組裝）；保留 `_handle_confirmation` 不變

## 3. 合併三批次 + 共用內容引擎（notifier）

- [x] 3.1 `run_checks` 改為單次評估全部觸發條件（#1–#9），移除依 mode 分流
- [x] 3.2 #6 維持 `is_weekday`；#5 視為惰性（由 #4 涵蓋）
- [x] 3.3 抽出共用函式 `build_daily_messages_for_user`：給定 uid → 組裝其今日內容（supervisor 另含摘要＋確認卡），供 push 與 on-demand 共用
- [x] 3.4 `_pending_confirmations()` 多撈 `id`(cid)、`board_id`、`card_name`＋claimer 顯示名；新增 `_all_project_names` by `board_id`（查無→後備值）
- [x] 3.5 確認卡 bubble 型別：專案名＋卡片名＋label＋標記人＋確認/退回 postback(cid)；排序優先避免截斷

## 4. 主動 push 僅送 vendor + skip-empty（notifier cron）

- [x] 4.1 `run_daily_push` 過濾收件人 `role = vendor` 才送（`_roles_by_lineid`）；admin/employee/customer 不 push
- [x] 4.2 某 vendor 0 bubble → 不呼叫 `send_flex`
- [x] 4.3 移除 morning「無進行中工項仍送佔位訊息」行為（空摘要不佔 bubble）
- [x] 4.4 `main()` 移除 noon/evening 進入點（保留相容但不送），保留單一每日執行（與 `test`）

## 5. Rich Menu on-demand 拉取（agent，reply＝免費）

- [x] 5.1 `setup_richmenu.py` 加「📋 今日提醒」區（postback `o=daily`）＋雙欄底圖（一次性註冊腳本，部署時執行）
- [x] 5.2 新增 `o=daily` postback handler `_handle_daily`：以共用內容引擎組裝請求者角色內容
- [x] 5.3 經 reply token 回覆（走既有 reply 優先/push fallback）；無內容回「今日無提醒」

## 6. 驗證

- [x] 6.0 本機單元驗證 `build_flex`：確認卡優先、cid 按鈕、專案+卡片+label 呈現、空摘要不佔位（py_compile 全通過）
- [x] 6.1 廠商標記某工項 → Trello 暫定生效、建立含 card_name 的 pending、**未**即時推主管、廠商收到暫定回覆（card_name 欄已確認）
- [x] 6.2 跑每日 push → 僅 role=vendor 收到；admin/employee/customer 不收（dry-run：9 有內容→僅 6 vendor 推）
- [x] 6.3 主管點 Rich Menu「今日提醒」→ 經 reply 收到摘要＋可操作確認卡（使用者已實機確認）
- [x] 6.4 點確認/退回 → 走既有 `cid` 追認/退回（handler 未變）
- [x] 6.5 board_id 非 active → 確認卡顯示後備專案名（「（未登錄專案）」）、卡片照常、不報錯
- [x] 6.6 vendor 無內容 → 不 push；任一使用者拉取無內容 → 回「今日無提醒」
- [x] 6.7 ~~核對 `_internal_recipients()` 去重 line_id（3 vs 4 帳號）~~ → moot：使用者已移除多出的 employee

## 7. 部署（jg-base）

- [x] 7.1 trello-notifier 三 CronJob 收斂為一個 `trello-notifier-daily`（08:00 Sun–Fri；移除 noon/evening）
- [x] 7.2 bump image 至 `2b63d3b`（含後續 RBAC/UI 修正），同步 deploy.yaml / admin.yaml / cronjobs.yaml；跑 `setup_richmenu.py --replace`（CJK 標籤）
- [x] 7.3 部署後驗證：pods 健康、每日 push 僅 vendor、各角色拉取內容正確（含 RBAC 隔離）
