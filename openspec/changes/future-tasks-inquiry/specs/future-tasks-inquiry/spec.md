## ADDED Requirements

### Requirement: 未來工項區間清單
系統 SHALL 提供「未來工項」查詢:列出選定**方向×視窗**內、**未完成**、且**開始日或結束日**落在該區間的帶 `[@]` 標記工項,依最早相關日期升序。方向 `∈ {未來, 過去}`;視窗 `∈ {2週, 1月, 2月, 3月}`(以天數近似 14/30/60/90):未來=`[今天, 今天+n]`、過去=`[今天-n, 今天]`。**每個任務僅列一次**(不因開始/結束分列兩筆),**精簡為一行**、依 **who–when–what** 排序:`@負責人 · 日期區間 · 任務描述`。負責人為 `[@(alias)]` 之 alias(可多個,如 `@水鋼@larry`);日期區間:同時有開始與結束→`MM/DD–MM/DD`、僅開始→`MM/DD 起`、僅結束→`至 MM/DD`;任務描述取 tag label 去除「：/:」後冗長說明(過長截斷)。內容以 **Reply API（免費）**回覆。

**呈現格式**:**一專案一欄**——以 **carousel** 呈現,每個專案(`public_label`)一個 **bubble**,專案名為 bubble 標頭(標頭另附「意念情境・{視窗}工項｜依目前進度推算」)。bubble 內為該專案各卡片:卡片名(粗體,只出現一次)其下每個 tag **一行**(`@負責人 · 日期區間 · 任務描述`,who–when–what);同卡多 tag 合併於該卡底下。專案數超過 12 時截斷並提示縮小視窗。

#### Scenario: 每任務一筆、精簡一行
- **WHEN** 某工項 `[@(sa),20260727-20260911] 主管機關檢查(6w)` 的開始與結束皆在區間
- **THEN** 僅列一筆,一行 `@sa · 07/27–09/11 · 主管機關檢查(6w)`(who–when–what;不分開始/到期兩列、不含冗長說明)

#### Scenario: 僅開始日 / 僅結束日
- **WHEN** 工項只有開始日(或只有結束日)且落在區間
- **THEN** 日期分別為 `MM/DD 起`(僅開始)或 `至 MM/DD`(僅結束)

#### Scenario: 同卡多 tag 合併
- **WHEN** 同一張卡有多個 tag 落在區間(如「合約簽訂」卡的水電/木工/…多個簽約)
- **THEN** 該卡以單一單元呈現,卡片標頭只出現一次,其下依序列出各 tag(每筆一行)

#### Scenario: 過去方向
- **WHEN** 使用者選「過去 2週」
- **THEN** 系統列出開始/結束日落在 `[今天-14天, 今天]`、未完成的工項,依日期升序

### Requirement: 未註冊 alias 工項不列入（對齊工期表有效 alias）
工項 owner 的 alias 若**未定義於 `line_users`（人員管理）**,該工項 MUST NOT 出現於未來工項清單——與**工期表有效 alias** 及 LINE「查無對應」採**同一來源判定**。工項有**任一** owner 未註冊(如 `[@(木??)]`)即整筆略過;所有 owner 皆註冊者才列入。DB 不可用時 graceful 不過濾。

#### Scenario: 未註冊 owner 的工項被濾掉
- **WHEN** 某工項標記 `[@(木??)]`（`木??` 不在 `line_users.alias_name`）
- **THEN** 該工項 MUST NOT 出現在未來工項清單

#### Scenario: 已註冊 owner 的工項列入
- **WHEN** 某工項標記 `[@(水鋼)]`（`水鋼` 在 `line_users.alias_name`）
- **THEN** 該工項可列入（其餘條件符合時）

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

### Requirement: 文字關鍵字備援（繞過 AI）
使用者以**文字**輸入「未來/過去 + 視窗」(如「未來工項」「未來2月工項」「未來二月」「過去2週」;支援阿拉伯與中文數字、視窗選 2週/1月/2月/3月;純「未來/過去」→ 預設未來/過去1月)時,系統 SHALL **直接走 `o=future` 同一份清單**,MUST NOT 送進 Claude(避免 AI 額度不足或延遲時無法查詢)。非此類文字則不攔截,照既有流程(今日/說明關鍵字或 Claude)。

#### Scenario: 打字查未來工項不經 AI
- **WHEN** 使用者輸入「未來2月工項」或「未來二月」
- **THEN** 系統以 future×60天 直接回未來工項清單,不呼叫 Claude

#### Scenario: 非未來關鍵字不受影響
- **WHEN** 使用者輸入一般問句(非未來/過去區間關鍵字)
- **THEN** 照既有流程處理(不被未來工項攔截)

### Requirement: 空區間與錯誤處理
選定區間無任何工項時,系統 SHALL 回覆可辨識的「(方向 視窗) 內無工項」訊息並仍附方向×視窗 quick-reply。方向/視窗參數缺失或非法時,系統 MUST NOT 崩潰,SHALL 回退為預設(未來 1月)。

#### Scenario: 空區間
- **WHEN** 選定區間計算後無工項
- **THEN** 回覆「(方向 視窗) 內無工項」並含 quick-reply

#### Scenario: 參數非法回退
- **WHEN** postback 的 `dir`/`n` 缺失或非法
- **THEN** 回退為未來 1月,不崩潰
