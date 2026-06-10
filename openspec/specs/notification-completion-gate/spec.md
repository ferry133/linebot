## Purpose
定義工程通知（`trello_line_notifier.py`）的到期／逾期條件如何尊重「完成狀態」：完成嚴格以 Trello 打勾判定，清單名稱不作為抑制依據，並對「完成但未歸欄」提供提醒。

## Requirements

### Requirement: 標記項目的完成判定

只有帶 `[@(...)]` 標記的項目才是「檢查項」，分兩種載體；其完成與否 SHALL **僅**以打勾狀態判定：

- **card 本身**（標記位於 card description）→ 完成 iff `dueComplete == true`。
- **to-do**（標記位於 checklist 項目）→ 完成 iff 該項目 `state == "complete"`。

清單名稱、未帶標記的 to-do 勾選狀態，MUST NOT 作為「完成」的判定依據。

#### Scenario: card 標記未打勾即未完成
- **WHEN** card description 帶標記，但 `dueComplete` 非 true（含 None）
- **THEN** 該 card 標記視為未完成，無論卡片在哪個清單欄、無論其未標記 to-do 是否勾選

#### Scenario: to-do 標記依自身勾選
- **WHEN** checklist 項目帶標記
- **THEN** 其完成與否僅取決於該項目 `state == "complete"`

### Requirement: 到期／逾期通知尊重完成狀態

到期與逾期類通知（#3 結束日倒數、#4 今日到期、#5 今日已逾期、#6 逾期天數）SHALL 僅在該標記項目**未完成**時發送；完成即不發送。開始日通知（#1、#2）不受影響，行為 MUST 維持不變。清單名稱 MUST NOT 作為抑制條件。

#### Scenario: 已打勾的項目不再到期/逾期提醒
- **WHEN** 標記項目已完成（card `dueComplete=true` 或 checklist `state=complete`）、結束日已到或已過
- **THEN** 不發送 #3～#6 通知

#### Scenario: 未打勾的項目照常提醒
- **WHEN** 標記項目未完成、結束日已到或已過、為平日（#6 限平日）
- **THEN** 照常發送對應的到期／逾期通知，無論卡片所在清單名稱

### Requirement: 完成但未歸欄的提醒

當一張卡片的**所有檢查項皆已完成**、但卡片**不在「已完成」欄**（清單名稱不含「已完成」）時，系統 SHALL 於 morning 每日摘要附加一則 **minor 警告**，列出該卡片，提醒歸欄。此為提醒性質，MUST NOT 改變任何通知的發送或抑制。

#### Scenario: 全完成但未歸欄 → 早報提醒
- **WHEN** 卡片至少有一個檢查項、且其所有檢查項皆完成、且清單名稱不含「已完成」
- **THEN** morning 摘要附加「✅ 已完成但未歸『已完成』欄」清單，列出 `board/card`

#### Scenario: 已歸欄不提醒
- **WHEN** 卡片所有檢查項完成、且清單名稱含「已完成」
- **THEN** 不產生此提醒

#### Scenario: 尚有未完成檢查項不提醒
- **WHEN** 卡片仍有任一檢查項未完成
- **THEN** 不產生此提醒（該未完成項另循 #3～#6 處理）
