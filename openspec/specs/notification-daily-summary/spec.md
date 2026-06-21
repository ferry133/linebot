## Purpose
定義每日工程摘要（morning #9）納入哪些帶標記工項並如何標示逾期：以 ±7 補完半開時間區間後，只收尚未完成且今天已到窗口起點的工項，逾期者以紅字標示。
## Requirements
### Requirement: 摘要以補完窗口納入未完成工項並標記逾期

每日工程摘要（morning #9）SHALL 先以 **±7 天**將工項標記的時間區間補成完整 `[start, end]`，再以補完後的窗口判斷納入與逾期標記：

**窗口補完規則：**
- 同時設有 `start` 與 `end`：原樣 `[start, end]`。
- 只有 `end`（`-YYYYMMDD`）：視為 `[end - 7 天, end]`。
- 只有 `start`（`YYYYMMDD-`）：視為 `[start, start + 7 天]`。
- 兩者皆無：視為無窗口。

**納入條件：** 工項 SHALL 納入摘要當且僅當**尚未完成**（card `dueComplete` 為否／checklist `state` 非 complete）且**執行當日 ≥ 補完後的 `start`**（即已到窗口起點；無上界，逾期者持續顯示直到完成）。

**逾期標記：** 凡**執行當日 > 補完後的 `end`** 的納入工項，SHALL 在摘要中標示「逾期」記號（紅色強調）。

已完成、未來才開始（執行當日早於補完後 `start`）、以及完全未設日期者 MUST NOT 出現在摘要中。此規則只作用於摘要內容收集與呈現，MUST NOT 改變 #1~#8 的通知判斷。

#### Scenario: 窗口內未完成的工項列入（未逾期不標記）
- **WHEN** morning run 遇到帶標記工項，執行當日落在補完後 `[start, end]` 內且尚未完成
- **THEN** 該工項收進摘要，且不顯示「逾期」記號

#### Scenario: 逾期未完成的工項列入並標記逾期
- **WHEN** morning run 遇到帶標記工項，執行當日晚於補完後 `end` 且尚未完成
- **THEN** 該工項收進摘要，並在該工項旁顯示「逾期」記號（紅色）

#### Scenario: 只有開始日且已過 start+7 仍未完成的工項列入並標記逾期
- **WHEN** morning run 遇到只有開始日（`YYYYMMDD-`，如 `[@(sa),20260530-]`）的工項，執行當日晚於 `start + 7 天` 且尚未完成
- **THEN** 該工項收進摘要並標記逾期

#### Scenario: 只有結束日且到期前 7 天內未完成的工項列入
- **WHEN** morning run 遇到只有結束日（`-YYYYMMDD`，如 `[@(bobo),-20260620]`）的工項，執行當日落在 `[end-7, end]` 內且尚未完成
- **THEN** 該工項收進摘要（未逾期，不標記）

#### Scenario: 只有結束日且距到期超過 7 天的工項不列入
- **WHEN** morning run 遇到只有結束日的工項，執行當日早於 `end - 7 天`
- **THEN** 該工項不被收進摘要（尚未進入補完窗口）

#### Scenario: 已完成的工項不列入
- **WHEN** morning run 遇到帶標記工項，該工項已打勾完成
- **THEN** 該工項不被收進摘要（不論是否在窗口內或逾期）

#### Scenario: 未來才開始的工項不列入
- **WHEN** morning run 遇到帶標記工項，執行當日早於補完後的 `start`（如 9 月才開始）
- **THEN** 該工項不被收進摘要

#### Scenario: 不影響 #1~#8 通知
- **WHEN** 某工項因不符納入條件而被排除於摘要
- **THEN** 其 #2「今日開始」、#5/#6「已逾期」等通知仍依各自條件於對應日觸發，不受摘要過濾影響

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

