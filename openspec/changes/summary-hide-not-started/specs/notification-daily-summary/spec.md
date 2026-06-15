## ADDED Requirements

### Requirement: 摘要納入已開始或逾期的未完成工項並標記逾期

每日工程摘要（morning #9）SHALL 僅納入**尚未完成**（card `dueComplete` 為否／checklist `state` 非 complete）且符合下列任一條件的帶標記工項：

1. **已開始**：工項設有開始日 `start` 且執行當日晚於 `start`（今天 > start）；或
2. **逾期**：工項設有結束日 `end` 且執行當日晚於 `end`（今天 > end）。

凡符合條件 2（逾期）的工項，其在摘要中 SHALL 標示「逾期」記號（以紅色強調）。

已完成、未來才開始（今天 ≤ start）、只有 `end` 但尚未到期（今天 ≤ end）、以及完全未設日期者 MUST NOT 出現在摘要中。此規則只作用於摘要內容收集與呈現，MUST NOT 改變 #1~#8 的通知判斷。

#### Scenario: 已開始未完成的工項列入（未逾期不標記）
- **WHEN** morning run 遇到帶標記工項，今天晚於 `start`、尚未過 `end`、且尚未完成
- **THEN** 該工項收進摘要，且不顯示「逾期」記號

#### Scenario: 逾期未完成的工項列入並標記逾期
- **WHEN** morning run 遇到帶標記工項，今天晚於 `end` 且尚未完成
- **THEN** 該工項收進摘要，並在該工項旁顯示「逾期」記號（紅色）

#### Scenario: 只有結束日且逾期未完成的工項列入並標記逾期
- **WHEN** morning run 遇到只有結束日（`-YYYYMMDD`）的工項，今天晚於 `end` 且尚未完成
- **THEN** 該工項收進摘要並標記逾期

#### Scenario: 只有開始日且已開始未完成的工項列入
- **WHEN** morning run 遇到只有開始日（`YYYYMMDD-`）的工項，今天晚於 `start` 且尚未完成
- **THEN** 該工項收進摘要（無 `end`，不標記逾期）

#### Scenario: 已完成的工項不列入
- **WHEN** morning run 遇到帶標記工項，該工項已打勾完成
- **THEN** 該工項不被收進摘要（不論是否在窗口內或逾期）

#### Scenario: 未來才開始的工項不列入
- **WHEN** morning run 遇到帶標記工項，今天早於或等於 `start`（如 9 月才開始）且未逾期
- **THEN** 該工項不被收進摘要

#### Scenario: 只有結束日但尚未到期的工項不列入
- **WHEN** morning run 遇到只有結束日（無開始日）的工項，今天尚未晚於 `end`
- **THEN** 該工項不被收進摘要

#### Scenario: 不影響 #1~#8 通知
- **WHEN** 某工項因不符納入條件而被排除於摘要
- **THEN** 其 #2「今日開始」、#5/#6「已逾期」等通知仍依各自條件於對應日觸發，不受摘要過濾影響
