## Why

「✅完成」按鈕是給不能碰 Trello 的廠商/客戶用的；admin/employee 改用 Trello 標記，其提醒卡已不顯示該按鈕（已上線於 image 9803392）。因此先前為防主管誤觸而加的「主管完成定案前二次確認（方案3）」**已無觸發點**（主管根本看不到完成鈕），成為多餘程式碼。

主管核可/退回廠商完成的流程**不變**：仍走 LINE「待主管確認」卡的 確認/退回（廠商標記為暫定 → 主管追認）。本案只移除多餘的方案3，並讓 spec 與已上線的「按鈕僅 vendor/customer」一致。

## What Changes

- **移除方案3**：`o=complete_confirm` / `o=complete_cancel` 路由、`_handle_status_update` 內主管二次確認 gate、`_complete_confirm_flex` / `_reply_complete_confirm`。
- **spec 對齊已上線行為**：提醒卡完成按鈕為**單顆「✅完成」**且**僅對 `role ∈ {vendor, customer}` 顯示**（admin/employee 不顯示）。
- **不動**：廠商/客戶一鍵暫定、「待主管確認」確認/退回核可流程、owner/supervisor 越權驗證與冪等。

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `trello-task-status-update`: 完成按鈕改為單顆且僅 vendor/customer 顯示；移除「主管完成定案前二次確認」要求。

## Impact

- `agents/customer_service.py`：移除方案3（路由 + gate + flex 兩個方法）；`complete` 改回 `op == "complete"`；`_handle_status_update` 廠商一鍵與主管核可（`_handle_confirmation`）不變。
- 顯示層（`build_flex` 的 `show_buttons` 角色判定）已於 #16 上線，本案不需再改 code，只補 spec。
- 無 DB / migration 變更。
