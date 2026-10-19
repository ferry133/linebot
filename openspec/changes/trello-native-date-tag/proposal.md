## Why

Trello 卡片已有原生「日期」欄位（開始日 + 到期日含時間），待辦項也有到期日。目前工項只認文字標記 `[@(代號),YYYYMMDD-YYYYMMDD:HHMM] 說明`（卡片描述第一行或待辦項名稱），日期得手打兩次、和 Trello 日曆/甘特各說各話。使用者已開始在卡片名稱寫 `108.[人造石@(石凱)] 施工` 並用 Trello 日期欄位排程（2026-10-19 量到 4 張卡，皆有日期；其中 3 張同時還留著舊描述標記），需要讓 linebot 認得這種寫法。

## What Changes

- 新增「原生日期」工項定義：
  - **卡片**：卡片名稱任一處含 `@(代號)`（可多個），日期取卡片的 `start`（開始日）與 `due`（到期日 + 時間，Asia/Taipei）。
  - **待辦項**：不是文字標記、且設有 Trello 到期日的待辦項就是工項；沒有日期的不追蹤。
    - 負責人：指派成員是公司帳號時歸公司，提醒管理者與員工。公司帳號是 `jiahdoper`，也就是 linebot 存取 Trello 用的帳號。
    - 沒有指派公司帳號時，繼承卡片名稱的 `@(代號)`。兩者都沒有，就不是工項。
    - Trello 待辦項只有到期日，所以等同舊寫法 `-YYYYMMDD:HHMM`，開始日沿用 ±7 補完。
  - 卡片沒有日期時，卡片本身不是工項，但名稱的 `@(代號)` 仍是卡片負責人，供卡內待辦項繼承。
  - 名稱有 `@(代號)` 卻沒設日期屬於錯誤設定。「今日提醒」的每日工程摘要會用警告區塊列出這類卡片，只有管理者和員工看得到。
  - 工項說明：卡片用名稱去掉 `@(代號)` 後的文字（`108.[人造石] 施工`），待辦項用自己的名稱。
- 舊文字標記 `[@(代號),日期區間] 說明` **照舊有效**，不 BREAKING。
- 同一張卡同時有兩種寫法時**以原生寫法為準**、描述標記忽略（一張卡只產生一筆工項，避免重複通知）。
- 所有讀工項的地方改用同一個解析入口：每日通知 #1–#9、今日提醒、未來工項詢問、trello-agent 查詢與 owner 過濾、✅完成/主管追認的目標比對、甘特圖。
- Trello 抓取欄位補上卡片的 `start,due` 與待辦項的 `due,idMember`。
- #7 停滯與 #8 全部完成，改以「卡內有任一工項」為前提；#8 的收件人改取卡片負責人。

## Capabilities

### New Capabilities
- `work-item-tag`: 定義什麼算一個「工項」——文字標記與 Trello 原生日期兩種寫法、各欄位（負責代號/開始/結束/時間/說明/完成狀態）的來源、兩者並存時的優先序。

### Modified Capabilities
（無。下游 spec——`consolidated-daily-notification`、`notification-daily-summary`、`role-based-access-control`、`trello-task-status-update` 等——都以「`[@(alias)]` 標記的工項」為前提；本 change 擴大「工項」的定義，而這些 spec 的觸發/可見性/完成規則本身不變。）

## Impact

- `trello_line_notifier.py`：`parse_tag` 旁新增卡片/待辦項層級的解析入口；`get_cards`/`get_card`/`get_board_full` 補欄位；`run_checks`（:608、:628、:663）與未來工項（:1033、:1039）改用新入口。
- `agents/trello_agent.py:111,122`、`agents/customer_service.py:748,754`（`_resolve_target`）改用新入口。
- `gantt_generator.py`：自帶一份 `ITEM_RE`/`parse_tag`，同步支援。
- **意念情境trello工期表**（`gantt_sheets_sync.gs`，Google Apps Script）：JS 版本的解析同步支援新寫法。部署方式是把檔案內容貼進 Apps Script，屬於人工步驟。
- 無 DB/migration、無新環境變數、無新依賴。
- 部署後，既有 4 張原生寫法的卡片，以及這些卡片中有 due 的待辦項，會開始進入通知。其中 3 張卡原本就經由描述標記進入通知，上線前要比對描述日期與 Trello 日期是否一致。
- 廠商可見範圍會擴大：卡片負責人是自己、而且設有日期的待辦項，都會看得到，並帶 ✅完成按鈕。指派給公司帳號的待辦項，廠商看不到。
