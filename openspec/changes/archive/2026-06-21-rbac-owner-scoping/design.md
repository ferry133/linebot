## Context

回溯記錄已上線的 RBAC 修正（image `2b63d3b`）。原本 vendor 只做板層授權（`_get_user_auth` 回該 vendor assigned 看板的 board_ids），同看板他人工項仍可見；且 `run_checks` 有 `larry→larryoffice` 鏡像，把主管內容複製給 vendor。

## Goals / Non-Goals

**Goals:** vendor 可見性收斂到 owner 層級，對話與通知兩路一致；移除跨帳號鏡像。
**Non-Goals:** 不改 customer（整看板）與 admin/employee（全部）；不改授權資料來源（仍 `line_user_projects`）。

## Decisions

**1. owner 過濾在兩條路徑分別落點**
- 對話：`customer_service._query_trello` 依 role 決定 `owner_alias`（vendor=自身 alias、其餘 None），帶進 MQTT；`trello_agent._query` 於板層過濾後再 `owner_alias in names` 過濾。`owner_alias=""`（vendor 無 alias）→ 匹配不到任何工項（安全預設，不外洩）。
- 通知/拉取：`run_checks` 產出 (uid, …)，每筆工項只送給其 sponsors（被 tag 者）與 internal；vendor 自然只拿到自己被 tag 的；主管摘要與確認卡僅 append 給 internal。

**2. 移除鏡像**
直接刪除 `run_checks` 末端的 larry→larryoffice 複製。要讓某帳號有主管視野，改設其 role=employee/admin（依角色，不硬編）。

## Risks / Trade-offs

- [vendor 無 alias → 查無工項] → 安全優先（不外洩）；屬資料設定問題，應補 alias。
- [customer 仍見整看板] → 刻意（屋主看案場全貌）；若日後要收斂，另案處理。
