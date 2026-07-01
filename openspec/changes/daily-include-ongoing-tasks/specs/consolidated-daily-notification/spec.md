## ADDED Requirements

### Requirement: 廠商每日內容含進行中工項
每位 vendor 收件人的每日內容（主動 push 與 on-demand 拉取）除 #1–#8 急迫觸發項外，SHALL 亦包含其被 `[@(alias)]` 標記、**符合 ±7 補完窗口**（沿用 `notification-daily-summary` 的 `_in_summary` 納入/逾期規則）、未完成的進行中工項。此內容與其急迫項合併於同一則整合 carousel；空內容（無急迫項亦無進行中）仍不主動 push。

#### Scenario: 廠商內容含窗口內進行中工項
- **WHEN** 某 vendor 有被 tag、在補完窗口內、未完成的工項（即使非 7 天內急迫）
- **THEN** 其每日 push／拉取內容包含這些進行中工項

#### Scenario: 未進窗口的未來工項不列入
- **WHEN** 某 vendor 被 tag 的工項執行當日早於補完後 `start`（未來才開始）
- **THEN** 該工項 MUST NOT 出現在其進行中內容（沿用窗口判定）

#### Scenario: 廠商完全無內容仍不送
- **WHEN** 某 vendor 既無急迫項亦無窗口內進行中工項
- **THEN** 系統不對其主動 push（skip-empty 不變）
