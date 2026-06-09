## ADDED Requirements

### Requirement: unresolved alias visibility

當 Trello 標記用到的名字在 `line_users.alias_name` 查無對應時，`trello_line_notifier.py` SHALL 在該次 run 收集這些未對應的名字（去重），並在 **morning 每日摘要（#9）** 尾端附加一段警告清單呈現給收件者（SA/Larry）。系統 MUST NOT 讓此訊號僅停留在 log。noon／evening 的行為 MUST 維持不變。

#### Scenario: 早報附加未對應清單
- **WHEN** morning run 期間，有一或多個 Trello 標記名字在 `line_users.alias_name` 查無對應
- **THEN** 每日摘要訊息尾端附加一段標題含「⚠️」的區塊，列出所有未對應的名字（去重）
- **THEN** 摘要仍正常發送給原本的收件者（SA/Larry）

#### Scenario: 無未對應時不顯示
- **WHEN** morning run 期間所有 Trello 標記名字都成功對應到 line_id
- **THEN** 每日摘要不含任何未對應警告段落（與本變更前的輸出一致）

#### Scenario: 非 morning 時段不改變行為
- **WHEN** noon 或 evening run 遇到未對應的 alias
- **THEN** 不產生面向使用者的未對應清單（維持既有行為，僅原有 log 警告）
