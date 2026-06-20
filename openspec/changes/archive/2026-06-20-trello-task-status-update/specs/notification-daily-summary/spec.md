## ADDED Requirements

### Requirement: 待主管確認清單呈現給主管

每日摘要（morning #9）對 supervisor（`role ∈ {admin, employee}`）收件者 SHALL 加列一段「待主管確認」清單，列出目前 `task_confirmations.status = pending` 的廠商暫定變更（工項 label、廠商、claim 時間）。非 supervisor 收件者 MUST NOT 看到此清單。此清單只附加於既有摘要，MUST NOT 改變既有工項納入與逾期標記規則。

#### Scenario: 有待確認時呈現給主管
- **WHEN** morning 摘要發給 supervisor 且存在 status=pending 的追認紀錄
- **THEN** 摘要加列「待主管確認」清單，列出各 pending 工項 label、廠商與 claim 時間

#### Scenario: 無待確認時不顯示
- **WHEN** morning 摘要發給 supervisor 且無任何 pending 追認紀錄
- **THEN** 摘要不含「待主管確認」清單

#### Scenario: 非主管不顯示
- **WHEN** morning 摘要發給非 admin/employee 收件者
- **THEN** 摘要不含「待主管確認」清單
