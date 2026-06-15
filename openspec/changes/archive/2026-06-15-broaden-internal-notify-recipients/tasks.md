## 1. 程式：解析全體管理者/員工

- [x] 1.1 在 `trello_line_notifier.py` 新增 `_internal_recipients() -> list[str]`，查 `line_users` WHERE `role IN ('admin','employee')` 回傳 line_id list；DB 不可用或無結果回 `[]` 並 log 警告。
- [x] 1.2 `check_item()` 簽名加參數 `internal: list[str]`，移除內部的 `sa_larry = _resolve_tag_recipients(["sa","larry"]) ...`，#3–#6 改用 `sponsors + internal`。
- [x] 1.3 `run_checks()` 開頭算一次 `internal = _internal_recipients()`，傳入每個 `check_item(...)` 呼叫點。
- [x] 1.4 #7 停滯通知：把 `_resolve_tag_recipients(["sa","larry"]) or [contacts.get("sa"), contacts.get("larry")]` 改為 `internal`。
- [x] 1.5 #9 每日摘要：把 `_resolve_tag_recipients(["sa","larry"]) or [...]` 改為 `internal`。

## 2. 文件同步

- [x] 2.1 更新 `trello-line-design.md` 觸發條件表「通知對象」欄：#3–#6 `sponsor + SA/Larry` → `sponsor + 所有管理者/員工`；#7、#9 `SA / Larry` → `所有管理者/員工`。
- [x] 2.2 檢查 design 文件其餘對「SA/Larry 收件人」的敘述是否需一致化（表格上方/下方說明文字）。

## 3. 驗證

- [x] 3.1 `python3 -c "import ast; ast.parse(open('trello_line_notifier.py').read())"` 通過；本機以無 DB 環境跑 `run_checks` 不 crash（internal=[]）。
- [x] 3.2 部署後在 pod 內載入改好的 `trello_line_notifier.py`，呼叫 `_internal_recipients()` 確認回傳的 line_id 集合 = admin/employee 全體（read-only，不真正群發）。
- [x] 3.3 一次實跑驗證 render（收件範圍限 larry+larryoffice），確認內部通知收件集合與預期一致。

## 4. 上線

- [x] 4.1 commit + push linebot；CI build。
- [x] 4.2 bump jg-base 全部 image pin（cronjobs.yaml ×3、deploy.yaml ×4、admin.yaml ×1、migrate-contacts-job.yaml ×1）→ Flux reconcile。
