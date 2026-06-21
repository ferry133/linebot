## Why

`role-based-access-control` 的「Permission lookup from DB」要求仍描述「對所有非 admin 角色都從 `line_user_projects` 查出 `allowed_board_ids` 帶給 trello-agent」。但 vendor 已改為**僅以工項標記過濾**（`allowed_board_ids=None`，owner_alias 為唯一依據），與此要求字面不符。補正 spec 使其與已上線行為（image `d6dbc94`）一致。

> 回溯記錄；程式碼已部署，僅補齊 spec。

## What Changes

- 「Permission lookup from DB」明訂 `allowed_board_ids` **依角色**決定：admin/employee=None；**vendor=None（不以板限制，改由 owner_alias tag 過濾）**；customer=line_user_projects 對應 active 看板（無則 []）；visitor=[]。
- 保留既有規範：一律從 `line_user_projects` JOIN `projects` 查詢、**不得**使用 `line_users.projects` JSONB；customer 無指派→[]→無權限。

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `role-based-access-control`: 細化「Permission lookup from DB」要求的 `allowed_board_ids` 取得規則為 per-role（特別是 vendor=None、tag-only）。

## Impact

- 已實作於 `agents/customer_service.py::_get_user_auth`。無程式碼/DB 變更，純 spec 補齊。
