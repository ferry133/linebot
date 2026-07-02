## ADDED Requirements

### Requirement: 未來工項區間清單
系統 SHALL 提供「未來工項」查詢:列出選定**方向×視窗**內、**未完成**、且**開始日或結束日**落在該區間的帶 `[@]` 標記工項,**依事件日期升序**排列,每筆標示「開始」或「到期」。方向 `∈ {未來, 過去}`;視窗 `∈ {2週, 1月, 2月, 3月}`(以天數近似 14/30/60/90):未來=`[今天, 今天+n]`、過去=`[今天-n, 今天]`。同一工項若開始日與結束日皆落在區間,SHALL 各列一筆事件。內容以 **Reply API（免費）**回覆。

#### Scenario: 列出區間內開始/到期工項
- **WHEN** 使用者選「未來 1月」
- **THEN** 系統列出結束日或開始日落在 `[今天, 今天+30天]`、未完成的工項,依日期升序,每筆標「開始」或「到期」

#### Scenario: 過去方向
- **WHEN** 使用者選「過去 2週」
- **THEN** 系統列出開始/結束日落在 `[今天-14天, 今天]`、未完成的工項,依日期升序

#### Scenario: 同工項開始與到期各一筆
- **WHEN** 某工項的開始日與結束日皆落在選定區間
- **THEN** 清單含該工項的「開始」與「到期」兩筆事件

### Requirement: 區間清單沿用 RBAC 且唯讀
未來工項清單 SHALL 沿用既有 RBAC 可見範圍:supervisor(admin/employee)全部、vendor 僅自己被 `[@(alias)]` 標記者、customer 僅其 `line_user_projects` 看板;MUST NOT 因此擴大或縮小。清單 MUST NOT 含「✅完成」等操作按鈕(唯讀);專案名一律用對外 `public_label`(去 PII)。

#### Scenario: vendor 只見自己的
- **WHEN** role=vendor 查未來工項
- **THEN** 僅列其被 tag 的工項;非其被指派者 MUST NOT 出現

#### Scenario: 唯讀無完成按鈕
- **WHEN** 呈現未來工項清單(任一角色)
- **THEN** 工項不含 ✅完成 按鈕

### Requirement: 投影語意與揭示
未來工項清單 SHALL 以**目前**各工項的完成/清單狀態為輸入,僅依所選區間的日曆判定開始/到期(即**投影/推算**,非歷史快照)。內容 SHALL 附「依目前進度推算」註記。

#### Scenario: 附推算註記
- **WHEN** 回覆未來工項清單
- **THEN** 內容含「依目前進度推算」註記

### Requirement: 方向與視窗切換(quick-reply)
未來工項回覆 SHALL 附 quick-reply 讓使用者切換:未來(2週/1月/2月/3月)與過去(2週/1月/2月/3月)各一組,以及「📅 指定日期」單日查詢入口。Rich Menu「未來工項」一級入口 SHALL 以預設(未來 1月)呈現。單日查詢沿用 `someday-reminder`(datetimepicker,過去/未來單日投影)。

#### Scenario: 切換視窗
- **WHEN** 使用者在未來工項清單點 quick-reply「未來 3月」
- **THEN** 系統改以 `[今天, 今天+90天]` 重列

#### Scenario: 轉單日查詢
- **WHEN** 使用者點「📅 指定日期」
- **THEN** 彈出 datetimepicker,選定日走 someday 單日投影

### Requirement: 空區間與錯誤處理
選定區間無任何工項時,系統 SHALL 回覆可辨識的「(方向 視窗) 內無工項」訊息並仍附方向×視窗 quick-reply。方向/視窗參數缺失或非法時,系統 MUST NOT 崩潰,SHALL 回退為預設(未來 1月)。

#### Scenario: 空區間
- **WHEN** 選定區間計算後無工項
- **THEN** 回覆「(方向 視窗) 內無工項」並含 quick-reply

#### Scenario: 參數非法回退
- **WHEN** postback 的 `dir`/`n` 缺失或非法
- **THEN** 回退為未來 1月,不崩潰
