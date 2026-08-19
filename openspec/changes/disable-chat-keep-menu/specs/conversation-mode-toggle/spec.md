## ADDED Requirements

### Requirement: 對話功能可逆開關

系統 SHALL 以環境變數 `CHAT_ENABLED` 控制客服自由對話（Claude agentic loop）是否啟用。未設定或設為任何非真值（`1`/`true`/`yes`/`on` 以外，大小寫不拘、前後空白忽略）時 SHALL 視為**關閉**（fail-closed）。設為真值時，文字訊息處理 SHALL 與開關導入前完全相同。

customer-service agent 啟動時 SHALL 於 log 輸出目前模式（`chat=enabled` 或 `chat=disabled`），使實際狀態可被直接量測而非由行為推論。

#### Scenario: 未設定環境變數
- **WHEN** 部署未提供 `CHAT_ENABLED`
- **THEN** 對話功能為關閉狀態
- **THEN** 啟動 log 含 `chat=disabled`

#### Scenario: 設為真值即恢復對話
- **WHEN** `CHAT_ENABLED=true`（或 `1`/`yes`/`on`）且 agent 重啟
- **THEN** 一般文字訊息照常進入 Claude 五步循環並可使用 `query_trello`／`get_project_photos`／`escalate_to_manager`
- **THEN** 啟動 log 含 `chat=enabled`

#### Scenario: 無法辨識的值不得意外啟用
- **WHEN** `CHAT_ENABLED` 設為空字串或拼錯的值（如 `ture`、`enabled`）
- **THEN** 對話功能維持關閉，且不呼叫 Claude

### Requirement: 關閉時以固定訊息回覆一般文字

對話功能關閉時，收到**未命中保留入口**的文字訊息，系統 SHALL 回覆一則固定引導訊息，內容 SHALL 說明客服對話暫停、SHALL 告知訊息已轉交專人、並 SHALL 指引使用「今日提醒」「未來工項」「使用說明」。該回覆 SHALL 走既有出口（優先 Reply API，失敗才 Push），且 SHALL NOT 讓使用者無回覆。

#### Scenario: 一般提問取得引導訊息
- **WHEN** 對話關閉且使用者傳「請問我家工程進度到哪了？」
- **THEN** 使用者收到固定引導訊息，內容含三個可用功能名稱與「已轉交專人」說明
- **THEN** 該回覆使用該次 webhook 的 reply token（免費）送出

#### Scenario: 未知角色也會收到回覆
- **WHEN** 對話關閉且未登錄使用者（visitor）傳送任意文字
- **THEN** 仍收到同一則固定引導訊息

### Requirement: 關閉時不得產生對話副作用

對話功能關閉時，處理一般文字訊息 SHALL NOT 呼叫 Anthropic API、SHALL NOT 委派 `query_trello` 給 trello-agent、SHALL NOT 執行 Claude 的 `escalate_to_manager` 工具（該工具隨對話一起停用），且 SHALL NOT 寫入 `working_memory`、`episodes` 或 `knowledge`。對主管的通知一律經下述「來訊轉發」要求，而非工具呼叫。

#### Scenario: 零 LLM 呼叫
- **WHEN** 對話關閉期間收到多則一般文字訊息
- **THEN** 該期間 Anthropic API 呼叫數為 0

#### Scenario: 記憶不被停用期間的訊息污染
- **WHEN** 對話關閉期間使用者持續傳訊息
- **THEN** `working_memory`／`episodes`／`knowledge` 無新增紀錄
- **THEN** 之後恢復對話時，記憶延續停用前的狀態

### Requirement: 關閉時將來訊轉發主管

對話功能關閉時，系統 SHALL 將該筆未命中保留入口的文字原文轉發給主管：優先送 `LINE_NOTIFY_GROUP_ID`；未設定時 SHALL 送給 `line_users` 中 `role='admin'` 的使用者，若無 admin 才退 `role='employee'`。SHALL NOT 以聯絡簿（contacts）的固定名字（如 `sa`／`larry`）作為對象來源——該對映以顯示名為 key，比對 alias 永遠落空，會造成「看起來已通知、實際沒人收到」。轉發內容 SHALL 含發生時間、來源使用者顯示名（有 alias 時併同呈現）、角色、來源為一對一或群組、以及原文（可截斷）。

當該訊息的來源即主管通知群本身時，系統 SHALL NOT 轉發（避免把該群訊息推回同一群造成回音）；此判定 SHALL 以 gateway 帶入的來源群組/聊天室 id 為依據。

轉發 SHALL NOT 阻塞訊息處理迴圈，且轉發失敗 SHALL NOT 影響已送出的使用者回覆。轉發 log SHALL 記錄**實際送達的對象數**（LINE API 非 200 不計入），並在 0 送達時留下 warning；「因來源為通知群而跳過」SHALL 另有 log。同一出口 SHALL 同時供 `escalate_to_manager` 使用，兩者不得各自維護一份對象清單。

#### Scenario: 一對一提問轉給主管群
- **WHEN** 對話關閉且客戶在一對一傳「浴室磁磚什麼時候貼？」
- **THEN** 主管通知群收到一則轉發，內含原文、該客戶顯示名/alias、角色與時間
- **THEN** 客戶本人同時收到固定引導訊息

#### Scenario: 來自主管通知群的訊息不轉發
- **WHEN** 對話關閉且訊息來源群組即 `LINE_NOTIFY_GROUP_ID`
- **THEN** 不產生轉發
- **THEN** log 記錄「來源為通知群、略過轉發」

#### Scenario: 其他群組來訊標記為群組
- **WHEN** 對話關閉且訊息來自非通知群的群組
- **THEN** 轉發內容標記其來源為群組

#### Scenario: 未設定通知群時送 admin
- **WHEN** 對話關閉、`LINE_NOTIFY_GROUP_ID` 未設定且收到一般文字訊息
- **THEN** 轉發送給 `line_users` 中所有 `role='admin'` 者（不含 employee）

#### Scenario: 沒有 admin 才退 employee
- **WHEN** `LINE_NOTIFY_GROUP_ID` 未設定且 `line_users` 無 admin
- **THEN** 轉發送給 `role='employee'` 者

#### Scenario: 沒有任何對象時留下警告
- **WHEN** `LINE_NOTIFY_GROUP_ID` 未設定且查無 admin/employee
- **THEN** 不送出訊息
- **THEN** log 留下 warning，使「沒人收到」不會讀起來像「已通知」

#### Scenario: 保留入口不觸發轉發
- **WHEN** 對話關閉且使用者輸入「今日提醒」或點選 Rich Menu
- **THEN** 不產生任何轉發

### Requirement: 關閉時保留的入口

對話功能關閉 SHALL NOT 影響下列入口，其行為與 RBAC 過濾一律維持不變：

- Rich Menu postback：`o=daily`（今日提醒）、`o=future`（未來工項）、`o=guide`（使用說明）、`o=someday`（指定日期）
- 文字關鍵字備援：`GUIDE_KEYWORDS`、`DAILY_KEYWORDS`、未來/過去工項關鍵字
- 工項狀態 postback：`o=complete`／`o=incomplete`，以及主管追認 `o=confirm`／`o=reject`
- 每日 CronJob 的 vendor-only 主動推播

#### Scenario: Rich Menu 三格照常運作
- **WHEN** 對話關閉且使用者點選「今日提醒」「未來工項」「使用說明」
- **THEN** 各自回覆對應內容，與開關導入前相同

#### Scenario: 關鍵字備援照常運作
- **WHEN** 對話關閉且使用者輸入「今日提醒」「使用說明」或「未來兩週工項」
- **THEN** 回覆對應的 Flex 內容，而非固定引導訊息

#### Scenario: 完成與追認不受影響
- **WHEN** 對話關閉且廠商點「✅完成」、主管點「確認／退回」
- **THEN** Trello 寫入、`task_confirmations` 建立/結案、權限檢查一如既往

#### Scenario: 每日推播不受影響
- **WHEN** 對話關閉期間每日 CronJob 於 08:00 執行
- **THEN** vendor 仍收到每日整合提醒
