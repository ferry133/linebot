## ADDED Requirements

### Requirement: 對外專案標籤不含 PII
系統 SHALL 提供對外（LINE 顯示用）的專案標籤 `public_label`，格式為 `{site_name}-{project_type}`，**MUST NOT** 包含 `owner_name`（屋主姓名）或其他 PII。當專案缺 `site_name` 或 `project_type`（legacy）時，SHALL 以 `case_number` 作為後備標籤；後備值亦 MUST NOT 含屋主姓名，且 MUST NOT 回退為 `projects.name` 或 Trello 看板原名。

#### Scenario: 一般專案標籤
- **WHEN** 取某專案的對外標籤，且其 site_name=「創世紀M3」、project_type=「室內裝修」
- **THEN** public_label =「創世紀M3-室內裝修」（不含屋主名）

#### Scenario: 缺結構欄位的後備
- **WHEN** 某 legacy 專案 site_name 或 project_type 為空
- **THEN** public_label 使用 case_number（如「115年第3案」），MUST NOT 顯示 projects.name 或 Trello 看板原名

### Requirement: 所有 LINE 顯示一律使用對外標籤
所有面向 LINE 使用者呈現專案/看板名稱的路徑——每日通知標頭、每日摘要、待主管確認卡、`query_trello` 查詢回覆、Rich Menu on-demand 拉取——SHALL 一律使用 `public_label`。系統 **MUST NOT** 對任何 LINE 使用者（**含 admin/employee**）顯示含屋主姓名的 `projects.name` 或 Trello 看板原名。需查屋主姓名者改於 Trello 或 admin UI 進行。Trello 看板原名本身不變（僅不在 LINE 呈現）。

#### Scenario: 廠商看到去識別標籤
- **WHEN** role=vendor 於任何 LINE 路徑看到其工項所屬專案
- **THEN** 顯示 public_label（如「創世紀M3-室內裝修」），不含屋主名

#### Scenario: 主管在 LINE 也不顯示屋主名
- **WHEN** role∈{admin,employee} 於每日摘要、確認卡或查詢回覆看到專案
- **THEN** 顯示 public_label；MUST NOT 顯示屋主姓名（要查屋主請至 Trello / admin UI）

#### Scenario: 不回退看板原名
- **WHEN** 某工項所屬 board 在對照表中查無 public_label
- **THEN** 使用 case_number 後備，MUST NOT 回退顯示 Trello 看板原名
