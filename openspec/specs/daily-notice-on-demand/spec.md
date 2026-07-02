# daily-notice-on-demand Specification

## Purpose
TBD - created by archiving change supervisor-confirm-card-context. Update Purpose after archive.
## Requirements
### Requirement: Rich Menu 提供每日內容拉取入口

系統 SHALL 提供一個常駐 LINE Rich Menu，內含「📋 今日提醒」項目，其 action 為 postback `data` 含 `o=daily`。所有與 bot 互動的使用者皆可隨時點按以拉取自己的每日內容。Rich Menu 為單一預設選單即可，呈現內容由回覆時依使用者角色決定。

#### Scenario: 點按今日提醒
- **WHEN** 使用者點按 Rich Menu 的「今日提醒」
- **THEN** 系統收到 `o=daily` postback，並回覆該使用者的每日內容

### Requirement: 拉取內容依角色組裝並以 Reply API 回覆

收到 `o=daily` 時，系統 SHALL 以與每日批次相同的內容引擎組裝**該請求者角色對應**的每日內容：vendor／customer 得其工項提醒、supervisor（admin/employee）得每日摘要與**可操作確認卡**（見 `notification-daily-summary`）。回覆 SHALL 依 `line-message-delivery`，於有 reply token 時走 **Reply API**（免費、不計推播額度），無可用 token 或 reply 失敗時 fallback Push。此拉取與每日主動 push 的內容定義一致，僅交付管道不同。

#### Scenario: 主管拉取得到確認卡
- **WHEN** supervisor 點按今日提醒
- **THEN** 回覆內容含其每日摘要與每筆 pending 的可操作確認卡（專案名＋卡片名＋label＋標記人＋確認/退回按鈕）

#### Scenario: 廠商/客戶拉取得到自身工項
- **WHEN** role=vendor 或 role=customer 使用者點按今日提醒
- **THEN** 回覆內容為該使用者當日的工項提醒

#### Scenario: 以 reply token 免費回覆
- **WHEN** 拉取請求帶有有效 reply token
- **THEN** 系統以 Reply API 回覆，不計入推播額度

#### Scenario: 無 token 時 fallback push
- **WHEN** 拉取請求無可用 reply token 或 reply 呼叫失敗
- **THEN** 系統改以 Push API 送出該內容（計入額度）

### Requirement: 拉取一律回覆

on-demand 拉取為使用者主動觸發，系統 SHALL 一律回覆，即使該使用者當日無任何應發內容亦回覆可辨識訊息（如「今日無提醒」）。此與主動 push 的「無內容不送」不同。

#### Scenario: 無內容仍回覆
- **WHEN** 使用者點按今日提醒但當日無任何應發內容
- **THEN** 系統回覆「今日無提醒」之類可辨識訊息（仍走 reply，免費）

### Requirement: Rich Menu 提供指定日期(someday)入口
Rich Menu SHALL 提供一格「查其他日期」作為 someday 提醒入口,採 **LINE datetimepicker（`mode=date`，`data=o=someday`）**;選定日經 postback 的 `params.date` 回傳。此入口與「今日提醒」「使用說明」並列於同一 Rich Menu。datetimepicker 不設 `initial/min/max`（靜態 Rich Menu 無法持有動態日期），每次點按以當下今日為預設、可選過去/未來日。**每日內容本身 MUST NOT 再放 datetimepicker 按鈕**（入口統一由 Rich Menu 提供，避免重複）。

#### Scenario: Rich Menu 有查其他日期入口
- **WHEN** 使用者開啟 Rich Menu
- **THEN** 有「查其他日期」一格,點按彈出日期選擇器 → 選定日回傳 `o=someday` + `params.date`

#### Scenario: 每日內容不含日期選擇器按鈕
- **WHEN** 使用者拉取今日或 someday 內容
- **THEN** 內容中 MUST NOT 出現 datetimepicker 按鈕（入口在 Rich Menu）

