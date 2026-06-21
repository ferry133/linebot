## 1. Spec 補正（已實作於 image d6dbc94）

- [x] 1.1 `_get_user_auth` vendor 回 `allowed_board_ids=None`（tag-only），customer 回 board 清單
- [x] 1.2 spec「Permission lookup from DB」以 per-role 表格明訂 allowed_board_ids
- [x] 1.3 保留 JSONB 禁用與 customer 無指派→[] 規範
