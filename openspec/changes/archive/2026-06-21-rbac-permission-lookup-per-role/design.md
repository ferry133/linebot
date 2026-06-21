## Context

回溯記錄已上線行為（image `d6dbc94`）。`_get_user_auth` 已改為 per-role 回傳 `allowed_board_ids`：admin/employee/vendor=None、customer=board 清單、其餘=[]。vendor 由 `owner_alias` tag 過濾，板層不設限。

## Goals / Non-Goals

**Goals:** spec 與 code 一致；明確 vendor=None（tag-only）。
**Non-Goals:** 不改 code；不改 customer/admin 行為；JSONB 禁用規範維持。

## Decisions

- 以表格列出 per-role `allowed_board_ids`，避免「所有非 admin 都查 board 清單」的舊字面。
- vendor 板層 None 但仍須 `owner_alias`——以一句話釘住「板層指派不影響 vendor 可見性、tag 為唯一依據」，與「廠商工項可見性以擁有者為界」要求呼應。

## Risks / Trade-offs

- [vendor 板層 None 看似較寬] → 實際由 tag 過濾收斂；未被 tag 即不可見，無外洩。
