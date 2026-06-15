## ADDED Requirements

### Requirement: 摘要僅納入未完成且窗口內或逾期的工項

每日工程摘要（morning #9）SHALL 僅納入**尚未完成**（card `dueComplete` 為否／checklist `state` 非 complete）且符合下列任一條件的帶標記工項：

1. **窗口內**：工項標記同時設有開始日 `start` 與結束日 `end`，且 `start <= 執行當日 <= end`（含端點）；或
2. **逾期**：工項標記設有結束日 `end`，執行當日晚於 `end`（`start` 可有可無，含只有 `end` 者）。

不符合者 MUST NOT 出現在摘要中——包括：**已完成**（不論窗口內或逾期）、未來才開始（執行當日 `< start`）、只有 `end` 但尚未到期、只有 `start` 無 `end`、以及完全未設日期者。此規則只作用於摘要內容收集，MUST NOT 改變 #1~#8 的通知判斷。

#### Scenario: 窗口內未完成的工項列入
- **WHEN** morning run 遇到帶標記工項，其 `start`、`end` 皆有設、`start <= 執行當日 <= end`、且尚未完成
- **THEN** 該工項收進摘要並依狀態欄分組顯示

#### Scenario: 窗口內但已完成的工項不列入
- **WHEN** morning run 遇到帶標記工項，今天雖落在 `[start, end]` 內，但該工項已打勾完成
- **THEN** 該工項不被收進摘要

#### Scenario: 逾期未完成的工項列入
- **WHEN** morning run 遇到帶標記工項，其 `end` 已過（執行當日晚於 `end`）且尚未完成
- **THEN** 該工項收進摘要（不論是否設有 `start`，含只有 `end` 者）

#### Scenario: 逾期但已完成的工項不列入
- **WHEN** morning run 遇到帶標記工項，其 `end` 已過但該工項已打勾完成
- **THEN** 該工項不被收進摘要

#### Scenario: 未來才開始的工項不列入
- **WHEN** morning run 遇到帶標記工項，其執行當日早於 `start`（如 9 月才開始）
- **THEN** 該工項不被收進摘要

#### Scenario: 只有結束日但尚未到期的工項不列入
- **WHEN** morning run 遇到帶標記工項，其標記只有結束日、無開始日，且執行當日尚未超過 `end`
- **THEN** 該工項不被收進摘要

#### Scenario: 只有開始日無結束日的工項不列入
- **WHEN** morning run 遇到帶標記工項，其標記只有開始日、無結束日
- **THEN** 該工項不被收進摘要

#### Scenario: 不影響 #1~#8 通知
- **WHEN** 某工項因不符納入條件而被排除於摘要
- **THEN** 其 #2「今日開始」、#5/#6「已逾期」等通知仍依各自條件於對應日觸發，不受摘要過濾影響
