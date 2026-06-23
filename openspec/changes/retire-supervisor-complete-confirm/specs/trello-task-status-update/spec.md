## MODIFIED Requirements

### Requirement: 透過提醒卡片按鈕更新工項完成狀態

提醒（#1–#8）的 Flex 卡片每則工項 SHALL 附**單顆「✅完成」** postback 按鈕，且**僅對 `role ∈ {vendor, customer}` 顯示**——admin/employee 改用 Trello 標記，其提醒卡 MUST NOT 附此按鈕。`data` 夾帶該工項的 `board_id`、`card_id`、`checkItem_id`（checklist 來源才有）、`source`（card/checklist）與 `op=complete`。使用者點按後，系統 SHALL 依該 id 精準定位並執行 Trello 寫入：checklist 工項改 `checkItem.state = complete`、card 層級工項（card desc tag）改 `card.dueComplete = true`；MUST NOT 移動卡片欄位、MUST NOT 變更日期或標記文字。取消完成（還原）不提供按鈕——請於 Trello 操作，或由主管於「待主管確認」卡按「退回」還原廠商的暫定變更。

#### Scenario: 廠商/客戶按完成標記 checklist 工項
- **WHEN** role∈{vendor,customer} 的 owner 點按某 checklist 工項的「✅完成」按鈕
- **THEN** 系統設定該 `checkItem.state = complete`
- **THEN** agent 回覆已將該工項標記完成

#### Scenario: 廠商/客戶按完成標記 card 層級工項
- **WHEN** role∈{vendor,customer} 的 owner 點按某 card 層級工項的「✅完成」按鈕
- **THEN** 系統設定該 `card.dueComplete = true`，且不移動卡片欄位

#### Scenario: 主管提醒卡不顯示完成按鈕
- **WHEN** role∈{admin,employee} 收到/拉取提醒卡
- **THEN** 卡片 MUST NOT 附「✅完成」按鈕（主管改用 Trello 標記）

#### Scenario: 冪等
- **WHEN** 目標工項已處於完成狀態又按「✅完成」
- **THEN** 系統不重複寫入，回覆該工項已是該狀態

## REMOVED Requirements

### Requirement: 主管完成定案前二次確認
**Reason**: admin/employee 的提醒卡已不顯示「✅完成」按鈕（改用 Trello 標記），主管不會在 LINE 點完成，二次確認流程無觸發點，成為多餘程式碼。
**Migration**: 主管改於 Trello 直接標記完成；廠商/客戶維持一鍵（暫定生效）；核可/退回廠商的暫定完成仍走 LINE「待主管確認」卡的 確認/退回（不變）。實作移除 `o=complete_confirm`/`o=complete_cancel` 路由、`_handle_status_update` 的 supervisor 二次確認 gate，以及 `_complete_confirm_flex`/`_reply_complete_confirm`。
