## 1. 移除方案3（agent）

- [x] 1.1 `_process_postback`：移除 `complete_confirm` 路由與 `complete_cancel` 分支（保留 `complete`/`incomplete` → `_handle_status_update`、`confirm`/`reject` → `_handle_confirmation`）
- [x] 1.2 `_handle_status_update`：`complete = (op == "complete")` 還原；移除「`op==complete` + supervisor → 回二次確認」的 gate
- [x] 1.3 移除 `_complete_confirm_flex` 與 `_reply_complete_confirm` 兩個方法

## 2. 驗證

- [x] 2.1 廠商/客戶點 ✅完成 → 一鍵暫定（不變）；主管提醒卡無完成鈕（#16 已驗）
- [x] 2.2 「待主管確認」確認/退回核可流程不受影響（`_handle_confirmation` 未動）
- [x] 2.3 py_compile 通過；無殘留 `complete_confirm`/`complete_cancel`/`_complete_confirm_flex` 參照

## 3. 部署

- [x] 3.1 bump customer-service image（`scripts/bump-linebot-image.sh`）
- [x] 3.2 部署後確認主管核可（確認/退回）正常、廠商一鍵正常
