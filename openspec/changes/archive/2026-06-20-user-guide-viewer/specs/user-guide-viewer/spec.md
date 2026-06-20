## ADDED Requirements

### Requirement: Rich Menu 使用說明入口

系統 SHALL 提供一個 LINE Rich Menu，含一顆「使用說明」按鈕，並設為**預設 rich menu**（所有加官方帳號好友者可見）。按鈕 SHALL 以 `action: postback`、`data` 帶 `o=guide` 觸發，使點擊回到 bot 處理。系統 SHALL 另接受關鍵字訊息（如「使用說明」）作為等效備援入口。

#### Scenario: 好友看到使用說明入口
- **WHEN** 一位已加官方帳號好友的使用者開啟聊天室
- **THEN** 聊天室底部 rich menu 顯示「使用說明」按鈕

#### Scenario: 點按送出 guide postback
- **WHEN** 使用者點按「使用說明」
- **THEN** LINE 送出 `postback` 事件，`data` 含 `o=guide`，並帶該使用者 `user_id` 與 `reply_token`

#### Scenario: 關鍵字備援
- **WHEN** 使用者傳送文字「使用說明」
- **THEN** 系統如同收到 `o=guide`，呈現其角色的線上說明

### Requirement: 依角色在對話內呈現線上說明

收到 `o=guide` 後，系統 SHALL 以 `user_id` 查 `line_users.role`，並在**對話內**（Reply API）呈現該角色對應手冊（`docs/<role>-guide.md`）的線上說明。五種角色 admin/employee/vendor/customer/visitor SHALL 各對應一份手冊；查無 `line_users` 記錄者 SHALL 視為 visitor。回覆 MUST NOT 消耗推播額度。系統 MUST NOT 開啟外部網頁、MUST NOT 要求 LIFF／登入／簽章連結。

#### Scenario: 員工看到員工線上說明
- **WHEN** role=employee 的使用者觸發 guide
- **THEN** 系統以 Reply API 在對話內回覆員工手冊的主題選單

#### Scenario: 各角色對應各自手冊
- **WHEN** role 為 admin/vendor/customer 之一的使用者觸發 guide
- **THEN** 回覆內容取自該角色的 `docs/<role>-guide.md`

#### Scenario: 查無記錄視為訪客
- **WHEN** 查無 line_users 記錄者觸發 guide
- **THEN** 回覆訪客（visitor）手冊的線上說明

#### Scenario: 不開網頁
- **WHEN** 使用者觸發 guide
- **THEN** 系統在對話內回覆，不回傳任何外部網頁連結、不要求登入或開啟 LIFF

### Requirement: 主題瀏覽、目前位置與完整手冊

線上說明 SHALL 提供以下視圖並可互相切換：(a)**主題選單**列出該手冊各 `##` 主題；(b)**單一主題**顯示該段內容並標示**目前位置 (i/N)**，附「上一／下一／目錄／完整手冊」導覽（首節無「上一」、末節無「下一」）；(c)**完整手冊**呈現整份內容，並在使用者目前所在段標示「你在這」。內容 SHALL 取自 `docs/<role>-guide.md` 的 `##` 分段。

#### Scenario: 從選單開啟某主題
- **WHEN** 使用者於主題選單點選第 i 個主題
- **THEN** 系統顯示該主題內容，header 標示位置 `(i/N)`，並提供上一/下一/目錄/完整手冊導覽

#### Scenario: 主題間前後切換
- **WHEN** 使用者在某主題點「下一」
- **THEN** 系統顯示下一主題；於最後一個主題時不顯示「下一」

#### Scenario: 完整手冊標示所在位置
- **WHEN** 使用者於某主題點「完整手冊」
- **THEN** 系統呈現整份手冊內容，並在該使用者剛才所在的主題標示「你在這」

#### Scenario: 隨時回目錄
- **WHEN** 使用者於單一主題或完整手冊點「目錄」
- **THEN** 系統回到主題選單

### Requirement: 手冊內容單一來源

線上說明內容 SHALL 即時取自 `docs/<role>-guide.md`，不另存第二份內容；markdown 以可讀方式轉為 LINE 文字。手冊更新 SHALL 只需修改對應 `docs/*.md` 並重建 image，線上說明即反映新內容。

#### Scenario: 內容取自 docs 來源
- **WHEN** 呈現某角色線上說明
- **THEN** 主題與內文取自 `docs/<role>-guide.md`

#### Scenario: 改 md 即更新
- **WHEN** 修改某 `docs/*.md` 並重新部署
- **THEN** 線上說明顯示更新後內容，無需改動其他檔案
