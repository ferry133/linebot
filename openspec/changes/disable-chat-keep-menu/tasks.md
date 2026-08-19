## 1. 開關與關閉時的回覆（customer_service）

- [x] 1.1 新增 module-level `CHAT_ENABLED = os.environ.get("CHAT_ENABLED", "false").strip().lower() in ("1","true","yes","on")`（fail-closed）
- [x] 1.2 新增固定引導訊息常數 `CHAT_DISABLED_NOTICE`：說明客服對話暫停、列出「今日提醒／未來工項／使用說明」、指引聯繫服務人員
- [x] 1.3 `_on_message`：在關鍵字分支之後、`_process()` 之前插入 `if not CHAT_ENABLED: self._reply(user_id, CHAT_DISABLED_NOTICE, reply_token); return`（postback 分支已在更前面 return，不受影響）
- [x] 1.4 `__main__` 啟動 log 加上 `chat=enabled|disabled`
- [x] 1.5 抽出 `_notify_managers(msg)`（`_escalate` 與轉發共用出口：通知群優先、回退 sa/larry）
- [x] 1.6 新增 `_forward_offline_message(user_id, text, group_id)`：組轉發訊息（時間/顯示名+alias/角色/一對一或群組/原文截 800 字）；來源為通知群時跳過；於背景 thread 呼叫
- [x] 1.7 `gateway/line_gateway.py`：message 事件的 inbox payload 增 `group_id`（`source.groupId` 或 `roomId`）
- [x] 1.8 `_manager_targets()`：通知群優先，未設定則查 `line_users` role=admin（無 admin 才 employee）；移除永遠落空的 contacts `sa`/`larry` 回退
- [x] 1.9 `_notify_managers()` 回傳實際送達數（非 200 不計），0 送達留 warning；轉發 log 改記送達數

## 2. 驗證（本機；腳本 `tests/smoke_chat_toggle.py`）

- [x] 2.1 單元驗證：`CHAT_ENABLED` 對 `""`/`ture`/`enabled`/未設定 → False；對 `1`/`true`/`TRUE`/`yes`/`on`/` true ` → True
- [x] 2.2 以假 broker 驗證關閉時：一般文字 → 只發出固定引導訊息，且未呼叫 anthropic client、未 publish `agents/trello/requests`、未寫 working_memory
- [x] 2.3 以假 broker 驗證關閉時：`使用說明`／`今日提醒`／`未來兩週工項` 三個關鍵字仍走各自 handler（非引導訊息）
- [x] 2.4 以假 broker 驗證關閉時：postback `o=daily`/`o=future`/`o=guide`/`o=someday`/`o=complete`/`o=confirm` 路由不變
- [x] 2.5 驗證 `CHAT_ENABLED=true` 時 `_on_message` 仍會進入 `_process`（恢復路徑未被破壞）且不轉發
- [x] 2.6 驗證轉發內容：含原文、`顯示名（alias）／角色`、一對一/群組標記；送到 `LINE_NOTIFY_GROUP_ID`
- [x] 2.7 驗證去回音：來源 group_id == 通知群 → 不轉發；其他群組 → 轉發並標記群組
- [x] 2.8 驗證未設 `LINE_NOTIFY_GROUP_ID` → 送 admin（無 admin 退 employee、查無主管不送）；HTTP 500 不計入送達數；並以 flask test_client 驗 gateway `group_id` 透傳（group/user/room 三種來源）
- [x] 2.9 在部署後的 pod 內以真 image 驗證路由與轉發（不對外送訊息）

## 3. 文件

- [x] 3.1 `CLAUDE.md`：在架構與環境變數表補上 `CHAT_ENABLED`（預設關閉）與恢復步驟（jg-base 設 `CHAT_ENABLED=true` + rollout）

## 4. 部署（人工把關）

- [ ] 4.1 PR → merge main → CI build image（記下 short sha）
- [ ] 4.2 jg-base：`scripts/bump-linebot-image.sh <sha>` → commit/push → `flux reconcile`（**由使用者確認後執行**，不動 migrate-contacts-job.yaml）
- [ ] 4.3 叢集驗證：customer-service pod log 出現 `chat=disabled`；LINE 實測一般文字→引導訊息＋主管群收到轉發（log `Forwarded offline msg`）、三格選單→內容正常
