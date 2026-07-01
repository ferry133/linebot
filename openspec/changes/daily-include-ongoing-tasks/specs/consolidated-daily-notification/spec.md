## ADDED Requirements

### Requirement: 廠商每日內容含進行中工項
每位 vendor 收件人的每日內容（主動 push 與 on-demand 拉取）除 #1–#8 急迫觸發項外，SHALL 亦包含其被 `[@(alias)]` 標記、在「執行中」清單、未完成的工項（見 `notification-daily-summary` 的「進行中工項納入與呈現」）。此內容與其急迫項合併於同一則整合 carousel；空內容（無急迫項亦無進行中）仍不主動 push。

#### Scenario: 廠商 push 含進行中工項
- **WHEN** 某 vendor 有被 tag 的執行中未完成工項（即使非 7 天內急迫）
- **THEN** 其每日 push／拉取內容包含這些進行中工項

#### Scenario: 廠商完全無內容仍不送
- **WHEN** 某 vendor 既無急迫項亦無進行中工項
- **THEN** 系統不對其主動 push（skip-empty 不變）
