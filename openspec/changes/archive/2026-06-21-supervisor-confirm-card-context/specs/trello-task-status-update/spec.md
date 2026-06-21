## MODIFIED Requirements

### Requirement: 廠商變更為暫定並待主管追認

當操作者為工項 owner 但**非** admin/employee（即廠商）時，其完成/取消變更 SHALL **立即在 Trello 生效（暫定）**，同時系統 SHALL 於 `task_confirmations` 建立一筆 `status=pending` 紀錄（記錄目標工項、claim 的目標狀態、操作者、時間，以及 claim 當下的**卡片名稱**快照）。系統 **MUST NOT** 於標記當下逐一即時推播主管；該 pending 改由 supervisor 的每日內容（經 on-demand 拉取，見 `daily-notice-on-demand` 與 `notification-daily-summary`）以可操作確認卡呈現。廠商標記後系統 SHALL 回覆廠商「已暫定，將通知主管確認」。

#### Scenario: 廠商標記完成為暫定
- **WHEN** 廠商（owner 非 supervisor）點按某工項「標記完成」
- **THEN** 系統立即將該工項在 Trello 設為完成
- **THEN** 系統建立一筆 pending 追認紀錄（含卡片名稱快照），並回覆廠商已暫定待主管確認

#### Scenario: 標記當下不即時推播主管
- **WHEN** 廠商建立一筆 pending 暫定變更
- **THEN** 系統 MUST NOT 於該當下推播任何主管確認卡片
- **THEN** 該 pending 於 supervisor 下次拉取每日內容時才呈現

#### Scenario: supervisor 直接標記免追認
- **WHEN** 操作者 role 為 admin 或 employee 並直接標記某工項完成/取消
- **THEN** 變更立即定案，系統 MUST NOT 建立 pending 追認紀錄、MUST NOT 要求再追認
