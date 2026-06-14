## Context

`trello_line_notifier.py` 目前在 4 個位置以 `_resolve_tag_recipients(["sa", "larry"])`（fallback 為 `contacts["sa"]`/`contacts["larry"]`）取得「內部收件人」：
- `check_item()` 的 `sa_larry`（#3–#6 到期/逾期）
- noon Checklist 停滯（#7）
- morning 每日摘要（#9）

`_resolve_tag_recipients` 走的是 `line_users.alias_name` 精確比對，因此內部通知永遠只送固定兩人。需求改為「所有管理者/員工」=`line_users.role IN ('admin','employee')` 的全體帳號。

DB 已有同型查詢可參考：`_load_contacts_from_db()`（依 role 查 `line_users`）、`_resolve_recipients_by_board_id()`（回傳 line_id list）。

## Goals / Non-Goals

**Goals:**
- 以單一 helper 解析 role IN ('admin','employee') 全體 line_id，取代 4 處硬編 `["sa","larry"]`。
- sponsor 解析、larry→larryoffice 鏡像、去重、completion gate 等其餘行為完全不變。
- 設計文件表格同步。

**Non-Goals:**
- 不改 sponsor（`@(...)` 標記）解析。
- 不改 #1/#2/#8（仍只給 sponsor）。
- 不加 DB 欄位、不做 migration、不改 alias 機制本身。

## Decisions

**D1：新增 `_internal_recipients()` helper，查 role IN ('admin','employee')。**
回傳 `list[str]`（line_id），DB 不可用或無結果時回 `[]` 並 log 警告（對齊 `_resolve_recipients_by_board_id` 的既有風格）。
- 為何不沿用 `load_contacts()`：那回傳的是 `{name: line_id}` 且包含 vendor/customer，語意不符（會把客戶/廠商也納入內部收件人）。專用查詢語意最清楚。
- 替代方案：保留 `sa/larry` 並「額外」加全體 admin/employee——否決，需求是「改為」而非「疊加」，且 sa/larry 本就是 admin/employee，疊加只會重複。

**D2：在 `run_checks()` 開頭解析一次，傳入 `check_item()`。**
`check_item()` 目前每次自行 `_resolve_tag_recipients(["sa","larry"])`（每個工項一次 DB 查詢）。改為在 `run_checks()` 算一次 `internal = _internal_recipients()`，以參數傳入 `check_item()`，#7/#9 直接用同一個 list。
- 好處：每次 run 只查一次（原本每工項查一次），減少 DB 往返；收件人集合在單次 run 內一致。
- 替代：維持 `check_item` 內部自查——否決，重複查詢且分散。

**D3：fallback 行為。**
DB 不可用時 `internal=[]`，內部通知（#3–#7、#9）該次不送內部份（與目前 sa/larry 查無時一致）。sponsor 份不受影響。不再保留 contacts.json 的 sa/larry fallback（該 fallback 只在無 DB 時有意義，而 role 查詢同樣需要 DB；語意上「所有管理者/員工」無法從 contacts.json 還原 role）。

## Risks / Trade-offs

- [收件人意外擴大／誤發] → 由 `line_users.role` 控管；admin/employee 名單即 admin web「用戶管理」可見且可調。上線後以一次實跑（送 larry+larryoffice 範圍驗證 render，不真正群發）確認收件集合符合預期。
- [DB 全無 admin/employee] → 內部通知靜默不送（僅 log）。可接受：與現況 sa/larry 查無一致；且實際 DB 必有 admin。
- [效能] → 改為每 run 查一次，較原先每工項查一次更省。

## Migration Plan

純程式碼變更，無資料變更。部署：push linebot → CI build → bump jg-base 全部 image pin → Flux reconcile。Rollback：還原 image pin 即可。
