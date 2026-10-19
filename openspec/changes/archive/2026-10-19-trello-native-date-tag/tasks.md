## 1. API 實測（API-first）

- [x] 1.1 以 pod 內唯讀查詢確認 `get_board_full` 的待辦項回傳中有 `due`、`idMember`；沒有的話，記下要補的 `checkItem_fields`
- [x] 1.2 確認 Trello 卡片「完成」圈圈對應的 API 欄位（請使用者在測試卡上切換一次，再讀 `dueComplete`），結果寫回 design 的 Open Questions
  - 2026-10-19 量到：預設回傳就有 `due`/`idMember`；`start`、`due` 只有加進 `card_fields` 才會回傳。完成圈圈對應 `dueComplete`，這點是推論，依據見 design 的 Open Questions

## 2. 解析入口

- [x] 2.1 `trello_line_notifier.py`：新增 `work_item_of_card(card)`、`work_item_of_checkitem(item)`
  - 依 spec 的優先序：卡片「原生 > 描述標記」；待辦項「文字標記 > 原生」
  - D3：原生寫法必須有日期
  - D3a：待辦項負責人以公司帳號優先，其次是卡片負責人；兩者都沒有就不是工項
  - 公司帳號 id 取自 `/members/me`，每個 process 快取一次；取不到時 fail-closed，指派給公司帳號的待辦項不當作工項，並記 log
  - D4：欄位對應，日期與時間一律轉成 Asia/Taipei
- [x] 2.2 `get_cards`、`get_card`、`get_board_full` 的 `card_fields` 補上 `start,due`；待辦項顯式帶 `due`
- [x] 2.3 新增 `tests/smoke_work_item_tag.py`，涵蓋 spec 每個 scenario
  - 示範卡的三個待辦項：一個繼承石凱、一個歸公司帳號、一個沒有日期
  - 過渡期卡片以 Trello 日期為準
  - 卡片名稱沒有 `@` 且待辦項沒有指派時，不算工項
  - 指派給公司以外的成員時，退回卡片負責人
  - 文字標記的待辦項不受 due 與指派成員影響
  - 先拿舊程式碼跑，確認原生寫法的 case 會失敗，證明測試分得出新舊版本

## 3. 改接所有讀取點

- [x] 3.1 `run_checks`（`trello_line_notifier.py:608`、`:628`）改用新入口；`raw` 與 `label` 改取自回傳值；公司負責的工項，sponsors 設為 internal
- [x] 3.2 #7 停滯與 #8 全部完成（`trello_line_notifier.py:646`–`:670`）改以「卡內有任一工項」為前提，#8 收件人依 D7
- [x] 3.2a 依 D8 在 `run_checks` 收集「名稱有 `@` 但沒日期」的卡片，加進 `warnings`；smoke test 要確認管理者看得到、廠商看不到
- [x] 3.3 未來工項詢問（`trello_line_notifier.py:1033`、`:1039`）改用新入口
- [x] 3.4 `agents/trello_agent.py:111`、`:122` 改用新入口；source 標示 `card_native`、`card_desc` 或 `checklist`
- [x] 3.5 `agents/customer_service.py` `_resolve_target`（`:748`、`:754`）改用新入口，讓 ✅完成與主管追認認得原生工項
- [x] 3.6 `gantt_generator.py` 改用共用入口（D6），補抓 `start,due`
- [x] 3.6a 工期表 `gantt_sheets_sync.gs` 依 D9 實作：
  - 新增 `workItemOfCard_`、`workItemOfCheckItem_`，取代 `parseTag_` 的兩處直接呼叫（`:179`、`:199`）
  - 補上抓取欄位
  - 公司帳號：負責人欄顯示「公司」，不套用 `hasUnmatchedOwner` 過濾
  - 以 node 跑一個本機小測試（stub `UrlFetchApp`），餵入示範卡資料，確認產出的列與 spec 的工期表 scenario 一致
- [x] 3.7 `grep -n "parse_tag(" -r --include='*.py' .`：除新入口內部之外，不應再有直接呼叫（`linebot_server.py` legacy 除外）

## 4. 上線前比對與文件

- [x] 4.1 從 pod 內以新、舊程式碼各列一次全部工項（唯讀）並比對差異。預期只有原生寫法的 4 張卡及其中有 due 的待辦項出現變化；列出過渡期 3 張卡描述日期與 Trello 日期的差異，請使用者確認
  - 2026-10-19 量到：20 個 active 看板，工項從舊版 110 筆變成新版 113 筆，共 4 處差異，都來自原生寫法：
    - `108.` 卡新增兩個待辦項：`丈量` 歸石凱，`下坎水槽` 歸公司
    - `109.[廚房人造石@(石凱)]` 卡片新增為工項
    - `180. [油漆@(油劉)] 修補`：描述標記寫 10/19–10/23，Trello 日期是 11/19–11/23，上線後依 Trello 日期 → 使用者已把 Trello 日期改成 10/19–10/23，並移除描述標記（23:08 查證）
  - 未完成、名稱有 `@` 卻未設日期的卡片：0 張。公司帳號查詢成功
- [x] 4.2 更新 `CLAUDE.md` 的「Trello 標記格式」一節，加上原生寫法與優先序

## 5. 部署與驗證

- [x] 5.1 PR → merge → CI → jg-base `bump-linebot-image.sh` → reconcile
- [x] 5.2 部署後在 pod 內確認 `108.[人造石@(石凱)] 施工` 以 Trello 日期出現在石凱的工項中
- [x] 5.2a （人工）使用者將新版 `gantt_sheets_sync.gs` 貼進工期表的 Apps Script，並執行一次 `syncTrelloGantt()`。執行前確認 Script Properties 的 Trello token 屬於 `jiahdoper`（D9）；執行後確認 `108.` 卡的三個待辦項呈現符合 spec
- [x] 5.3 使用者以 LINE「今日提醒」或對話查詢實測原生工項（人工）
