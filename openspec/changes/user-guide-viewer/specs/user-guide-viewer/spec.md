## ADDED Requirements

### Requirement: Rich Menu 使用說明入口

系統 SHALL 提供一個 LINE Rich Menu，含一顆「使用說明」按鈕，並設為**預設 rich menu**（所有加官方帳號好友者可見）。按鈕 SHALL 以 `action: postback`、`data` 帶 `o=guide` 觸發，使點擊回到 bot 處理而非開啟未帶身分的網頁。

#### Scenario: 好友看到使用說明入口
- **WHEN** 一位已加官方帳號好友的使用者開啟聊天室
- **THEN** 聊天室底部 rich menu 顯示「使用說明」按鈕

#### Scenario: 點按送出 guide postback
- **WHEN** 使用者點按「使用說明」
- **THEN** LINE 送出 `postback` 事件，`data` 含 `o=guide`，並帶該使用者 `user_id` 與 `reply_token`

### Requirement: 依角色派發對應手冊

收到 `o=guide` 後，系統 SHALL 以 `user_id` 查 `line_users.role`，並回覆**該角色對應手冊**的開啟連結。五種角色 admin/employee/vendor/customer/visitor SHALL 各對應一份手冊；查無 `line_users` 記錄者 SHALL 視為 visitor。回覆 SHALL 使用 Reply API（`reply_token`），MUST NOT 消耗推播額度。

#### Scenario: 員工取得員工手冊連結
- **WHEN** role=employee 的使用者觸發 guide
- **THEN** 系統以 Reply API 回覆一則含「開啟使用說明」連結的訊息，連結指向員工手冊

#### Scenario: 廠商取得廠商手冊連結
- **WHEN** role=vendor 的使用者觸發 guide
- **THEN** 回覆指向廠商手冊的連結

#### Scenario: 管理員取得管理員手冊連結
- **WHEN** role=admin 的使用者觸發 guide
- **THEN** 回覆指向管理員手冊的連結

#### Scenario: 客戶取得客戶手冊連結
- **WHEN** role=customer 的使用者觸發 guide
- **THEN** 回覆指向客戶手冊的連結

#### Scenario: 訪客取得訪客手冊連結
- **WHEN** role=visitor 的使用者觸發 guide
- **THEN** 回覆指向訪客手冊（歡迎與啟用說明）的連結

#### Scenario: 查無記錄視為訪客
- **WHEN** 查無 line_users 記錄者觸發 guide
- **THEN** 回覆指向訪客手冊的連結

### Requirement: 簽章連結保護檢視頁

派發給使用者的手冊連結 SHALL 夾帶一個短效簽章 token，編碼**角色**與**到期時間**，並以 `HMAC_SHA256(GUIDE_SIGNING_SECRET, 角色|到期)` 簽章。檢視頁 `GET /guide` SHALL 不要求 Basic Auth，但 MUST 驗證簽章正確且未過期，才渲染對應角色手冊；驗證失敗 SHALL 回 401/拒絕，MUST NOT 因此洩漏其他角色手冊。

#### Scenario: 有效 token 開啟對應手冊
- **WHEN** 使用者開啟 bot 發出、簽章有效且未過期的連結
- **THEN** 檢視頁渲染該 token 所編碼角色的手冊

#### Scenario: 過期 token 被拒
- **WHEN** 連結的 token 已超過到期時間
- **THEN** 檢視頁拒絕並回報連結已失效，不渲染任何手冊

#### Scenario: 竄改 token 被拒
- **WHEN** token 的角色或到期欄位被竄改、簽章對不上
- **THEN** 檢視頁回 401，不渲染任何手冊

#### Scenario: 無 token 直接造訪
- **WHEN** 直接造訪 `/guide` 不帶 token
- **THEN** 檢視頁拒絕存取

### Requirement: 手冊內容單一來源且手機友善

檢視頁 SHALL 即時將 `docs/<role>-guide.md` 渲染為手機友善（RWD）HTML 作為唯一內容來源；不另存第二份內容。手冊文字更新 SHALL 只需修改對應 `docs/*.md` 並重建 image，檢視頁即反映新內容。

#### Scenario: 渲染自 docs 來源
- **WHEN** 檢視頁渲染某角色手冊
- **THEN** 內容取自 `docs/<role>-guide.md`（image 內），以 RWD HTML 呈現

#### Scenario: 改 md 即更新
- **WHEN** 修改某 `docs/*.md` 並重新部署
- **THEN** 檢視頁顯示更新後內容，無需改動其他檔案
