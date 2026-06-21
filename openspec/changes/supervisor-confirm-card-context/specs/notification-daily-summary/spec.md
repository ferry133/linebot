## MODIFIED Requirements

### Requirement: 待主管確認清單呈現給主管

supervisor（`role ∈ {admin, employee}`）的每日內容 SHALL 加入目前 `task_confirmations.status = pending` 的廠商暫定變更。由於主管不再收主動 push，這些內容於主管 **on-demand 拉取**（見 `daily-notice-on-demand`）時呈現。每一筆 pending SHALL 呈現為一張**可操作確認卡**，內含：所屬**專案名稱**、所屬**卡片名稱**、工項 **label**、**標記人**（廠商顯示名/alias）、以及「✅ 確認 / ↩︎ 退回」兩個 postback 按鈕（`data` 夾帶該紀錄的 `cid`，按下後沿用既有追認/退回處理）。專案名稱 SHALL 由該紀錄的 `board_id` 解析（取 `projects.name`），無法對應 active 專案時以可辨識後備值呈現；卡片名稱取自 `task_confirmations.card_name` 快照。非 supervisor 收件者 MUST NOT 看到這些卡片。確認卡與其它摘要 bubble 共用同一則 Flex carousel；超過 carousel 上限時確認卡 SHALL 優先保留，溢出的 pending 於下次拉取再呈現。

#### Scenario: 主管拉取時呈現可操作卡片
- **WHEN** supervisor 拉取每日內容且存在 status=pending 的追認紀錄
- **THEN** 內容含每筆 pending 的確認卡，顯示專案名稱、卡片名稱、label、標記人與確認/退回按鈕

#### Scenario: 按卡片按鈕完成追認
- **WHEN** supervisor 於確認卡點按「確認」或「退回」
- **THEN** 系統依卡片夾帶的 `cid` 套用既有追認/退回處理（確認定案／退回還原）

#### Scenario: 專案名稱無法解析時的後備
- **WHEN** 某 pending 紀錄的 `board_id` 無法對應到任何 active 專案
- **THEN** 確認卡仍 MUST 顯示卡片名稱與 label，專案名稱欄位以可辨識後備值呈現，MUST NOT 省略卡片或使回覆失敗

#### Scenario: 無待確認時不顯示
- **WHEN** supervisor 拉取每日內容且無任何 pending 追認紀錄
- **THEN** 內容不含任何確認卡

#### Scenario: 非主管不顯示
- **WHEN** 非 admin/employee 使用者拉取每日內容
- **THEN** 內容不含任何確認卡
