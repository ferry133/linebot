## Context

工項今天只有一種定義：`ITEM_RE`（`trello_line_notifier.py:333`）比對**卡片描述第一行**或**待辦項名稱**開頭的 `[@(代號)…,YYYYMMDD-YYYYMMDD:HHMM] 說明`，回傳 `(names, start, end, end_time, label)`。這個 tuple 被 9 處各自取用：

| 位置 | 用途 |
|---|---|
| `trello_line_notifier.py:608` / `:628` | `run_checks` 卡片 / 待辦項 → #1–#6、#9 摘要 |
| `trello_line_notifier.py:663` | #8 全部完成 → 找通知對象 |
| `trello_line_notifier.py:1033` / `:1039` | 未來工項詢問 |
| `agents/trello_agent.py:111` / `:122` | 對話查詢的工項清單（owner 過濾吃 `names`） |
| `agents/customer_service.py:748` / `:754` | `_resolve_target`：✅完成 / 主管追認時重新驗證負責人 |
| `gantt_generator.py:38` | 自帶一份同樣的 regex |

2026-10-19 量測（唯讀，26 看板 / 1453 卡 / 2124 待辦項）：
- 卡片名稱含 `@(…)` 的 4 張，**4 張都有 Trello 日期**，其中 3 張描述第一行還留著舊標記（過渡期）。例：名稱 `108.[人造石@(石凱)] 施工`、日期 11/02 – 11/03 17:00、描述 `[@(石凱),20261102-20261103] 施工`。
- Trello API 的待辦項欄位只有 `due`、`dueReminder`、`idMember`，**沒有 `start`**（直接 GET 單一待辦項也沒有）。
- 示範卡 `108.` 的 3 個待辦項：
  - `丈量`：有 due、未指派。
  - `下坎水槽…`：有 due、指派成員為 `jiahdoper`。
  - `現場附帶安裝品…`：沒有 due。
- `jiahdoper` 就是 linebot 存取 Trello 所用 token 的擁有者：`GET /members/me` 回傳的 id 與待辦項的 `idMember` 相同。使用者口頭說的是 jiahd.oper。
- 2124 個待辦項中有 1393 個帶 `idMember`。抽查人數最多的前三個成員 id，`/members/{id}` 都回 404，可能是複製範本時留下的失效成員。全部只有 8 個待辦項有 due，所以這些失效的指派幾乎都落在不追蹤的項目上。
- 卡片日期格式：`start` 為 `…T00:00:00.000Z`（只有日期），`due` 為帶時間的 UTC（`T09:00Z` = 台北 17:00）。

## Goals / Non-Goals

**Goals:**
- 卡片名稱的 `@(代號)` 是卡片負責人。卡片設有 Trello 日期時，卡片本身是一筆工項。
- 卡內有 due 的待辦項是工項。指派成員是公司帳號時，負責人是公司；否則負責人是卡片負責人。
- 行為與等價的文字標記相同：#1–#9、±7、RBAC、完成流程都照舊。
- 9 個讀取點走同一個解析入口，不再各自讀 `desc` 或 `name`。
- 舊文字標記零行為變化。

**Non-Goals:**
- 不建立一般性的「Trello 成員 ↔ LINE 使用者」對照，因為廠商多半不是 Trello 成員。指派成員只認一個特例：公司帳號。卡片層級的 `idMembers` 不使用。
- 不回寫 Trello：不把描述標記同步成日期欄位，也不反向同步。
- 不改任何觸發條件、±7 補完窗口、可見性或完成流程的規則。

## Decisions

**D1. 新增卡片 / 待辦項層級的解析函式，取代直接呼叫 `parse_tag`。**
`work_item_of_card(card)` 與 `work_item_of_checkitem(item)` 回傳既有 tuple 再加一個 `raw`（給 `check_item` 的 raw 與確認快照用），找不到工項時回 `None`。`parse_tag` 保留為文字層的內部函式。
- 替代方案是在 `parse_tag(text)` 裡多吃日期參數。不採用：呼叫端仍要各自決定讀 `desc` 還是 `name`，而那正是這次要統一的分歧點。

**D2. 卡片的優先序：原生寫法優先，其次才是描述標記。** 名稱含 `@(…)` 而且有 `start` 或 `due` 時，用原生寫法，描述第一行忽略。否則走舊規則，讀描述第一行。
- 使用者的說法是「日期可由 Trello 日期欄位取代」，而 Trello 日期是排程真正在改的地方，描述標記會變成過期副本。
- 一張卡只產生一筆工項。若兩者各算一筆，過渡期的 3 張卡會重複通知。
- 替代方案是讓描述標記優先。不採用：過渡期描述標記與 Trello 日期不一致時，通知會跟著舊值走，而且使用者看不出原因。

**D3. 原生寫法以「有日期」作為追蹤條件。** 卡片沒有任何 Trello 日期時，卡片本身不是工項。待辦項沒有 due 時，不是工項。使用者的原話是：「有設定日期的才需要追蹤通知」。
- 舊標記允許 `[@(x),]` 不帶日期，但那需要刻意寫出 `[@…]`。原生寫法的待辦項名稱什麼都不用寫，只能靠日期判斷要不要追蹤。
- 卡片沒有日期時，名稱的 `@(代號)` 仍是卡片負責人，供卡內待辦項繼承。

**D3a. 待辦項負責人：公司帳號優先，其次是卡片負責人。**
- 指派成員是公司帳號時，負責人是公司，提醒對象為 `_internal_recipients()`（admin 與 employee）。工項的 `names` 為空，另外帶 `company=True`。
- 否則用卡片名稱的 `@(代號)`。兩者都沒有時，不是工項。
- 公司帳號取 `GET /members/me` 回傳的 id，每個 process 快取一次，不寫死 username，也不另加環境變數。這樣 token 換人時會跟著換，也不會把 `jiahd.oper`／`jiahdoper` 拼錯。
- 指派給其他成員一律忽略，回到卡片負責人。如此一來，量到的那些 404 失效成員不會讓工項失去負責人。
- `names` 為空時，廠商的 owner 過濾比對不到，所以廠商看不到這筆工項，也沒有 ✅完成按鈕。這符合「公司負責」的意思，RBAC 不必另外修改。
- 替代方案是用環境變數設定公司帳號的 username。不採用：多一個要同步的設定，而 token 擁有者本來就是這個帳號。

**D4. 欄位對應（全部轉成 Asia/Taipei）。**

| tuple 欄位 | 卡片原生 | 待辦項原生 |
|---|---|---|
| names | 名稱中所有 `@(x)`，轉小寫 | 指派給公司帳號 → `[]`，另帶 `company=True`；否則取卡片名稱的 `@(x)` |
| start | `start` 的台北日期 | `None`（API 沒有這個欄位，由 ±7 補完） |
| end | `due` 的台北日期 | `due` 的台北日期 |
| end_time | `due` 的台北時間 | 同左 |
| label | 名稱去掉 `@(…)`、收掉多餘空白（`108.[人造石] 施工`） | 待辦項名稱 |
| complete | `dueComplete` | `state == "complete"` |

- `@(x)@(y)` 與 `@(x) @(y)` 都接受。
- 標記式 regex 要求 `[@` 在開頭。原生式用 `@\(([^)]+)\)` 在卡片名稱裡全文搜尋。
- 待辦項名稱若符合舊的 `[@…]` 標記，仍走舊規則，due 與指派成員都不看，以免同一項被兩種寫法各解一次。
- `work_item_of_checkitem(item, card)` 需要所屬卡片（用來取卡片負責人）與公司帳號 id。

**D5. 抓取欄位。** `get_cards`、`get_card` 與 `get_board_full` 的 `card_fields` 補上 `start,due`。待辦項顯式要求 `checkItem_fields=name,state,due,idMember`，不依賴預設欄位。

**D8. 名稱有 `@` 但沒日期時列入警告。** 沿用 `run_checks` 既有的 `warnings` 機制（`trello_line_notifier.py:679`–`:695`），與「查無對應 LINE 帳號」「已完成但未歸欄」並列，新增一張「⚠️ 卡片已指定負責人但未設日期（請在 Trello 設定日期）」bubble，每行列出 `・{公開標籤}/{列表}/{卡片名稱}`。
- 這個機制本來就只給 internal（`:700`），不需要另外處理 RBAC。
- 使用者原話：「這是錯誤的設定，應該要搭配日期」。所以即使描述第一行仍有舊標記、可以退回舊規則解析，一樣要列入警告。
- 替代方案是把整張卡直接當作沒有日期的工項。不採用：那樣會讓錯誤設定看起來正常運作，使用者也就不會去補日期。

**D9. 工期表（`gantt_sheets_sync.gs`）以 JS 實作同一套規則。** 它跑在 Google Apps Script，無法 import Python，只能**複製規則**。為了不讓兩份實作分岔：
- `collectItems_()` 抽出 `workItemOfCard_(card, companyId)` 與 `workItemOfCheckItem_(item, card, companyId)`，名稱與分支順序對應 Python 版，並在註解指向 `openspec/specs/work-item-tag`。
- 抓取欄位補上 `start,due`，以及 `checkItem_fields=name,state,due,idMember`。
- 公司帳號取 `/members/me`。前提是工期表 Script Properties 的 Trello token 也屬於 `jiahdoper`；apply 時要確認，若不是，改以 Script Property `COMPANY_MEMBER` 指定。
- 公司負責的列，負責人欄顯示「公司」，並跳過 `hasUnmatchedOwner` 過濾（公司不是 LINE alias）。
- 原生卡片列沿用現有 desc 列的呈現方式（黃色、併入卡片摘要列）；只有結束日的待辦項沿用淡色 end-only bar。
- 「名稱有 `@` 但沒日期」的警告只放在 LINE 每日摘要，工期表不顯示：該卡在工期表上本來就沒有 bar 可畫。
- 部署方式不同：`.gs` 不走 CI 與 jg-base，需要使用者把檔案內容貼進 Apps Script 並執行一次 `syncTrelloGantt()`。這是人工步驟，見 tasks。
- 替代方案：讓工期表改呼叫 linebot 的 API 取得已解析的工項，從根本消除重複實作。不採用：會改變工期表的資料來源與可用性（linebot 停機時工期表跟著失效），超出本 change 範圍，可另開 change。

**D7. #7 停滯與 #8 全部完成。** 目前兩者都以「卡內有文字標記的待辦項」為前提，#8 的收件人也從待辦項標記找。改為以「卡內有任一工項（含原生寫法）」為前提，#8 的收件人改為卡片負責人；卡片沒有負責人時，改看各工項的負責人。

**D6. `gantt_generator.py` 改為 import 共用函式**，不再保留自己的 regex 副本。它本來就與 notifier 在同一個 image。若有 import 成本的顧慮，改成同步複製一份並加註，在 apply 時決定。

## Risks / Trade-offs

- [過渡期 3 張卡的描述日期與 Trello 日期不一致] → D2 之後通知跟著 Trello 日期走。上線前列出這 3 張卡兩邊的日期給使用者確認。
- [卡片名稱裡的 `@(…)` 不是要指派人，例如「@(備註)」] → D3 要求有日期，降低誤觸。若代號在 `line_users` 找不到對應，沿用現行行為：無收件人，只進主管摘要。
- [行為擴大：既有卡片中「有 due、沒有標記」的待辦項，若卡片名稱有 `@(…)` 或指派給公司帳號，部署後會開始產生提醒] → 全部只量到 8 個待辦項有 due，影響面小。任務 4.1 的新舊比對會逐筆列出。
- [公司帳號 id 取不到（`/members/me` 失敗）] → fail-closed：該次掃描記 log，指派給公司帳號的待辦項不當作工項，而不是退回卡片負責人。寧可漏一次提醒，也不要提醒錯人。
- [Trello 卡片的「完成」圈圈不一定等於 `dueComplete`] → 實作前用 API 實測：在 `108.` 卡上切換完成狀態後讀 `dueComplete`。若對不上，complete 改讀實際的欄位。這是 API-first 原則，沒有實測前不寫死。
- [`start` 只存日期，但以 UTC 00:00 表示] → 一律轉成台北時間再取日期。UTC 00:00 是台北 08:00，同一天，不會跨日出錯。
- [待辦項沒有開始日，只能套 ±7] → 與現行 `-YYYYMMDD` 寫法相同，屬已知、可接受的取捨。若之後 Trello API 提供待辦項 `start`，只需改 D4 表格中的一格。

## Migration Plan

1. 部署前，從 pod 內以新程式碼唯讀跑一次工項清單，與舊程式碼逐筆比較差異。預期只有 4 張原生卡的來源與日期改變，或新增。
2. 照一般 release 流程：PR → CI → `bump-linebot-image.sh` → reconcile。
3. 回滾：bump 回前一個 sha。沒有 DB 變更，也沒有寫回 Trello。

## Open Questions

- ~~Trello 卡片的「完成」圈圈對應哪個 API 欄位~~ → 2026-10-19 apply 時量到，結論是**推論**，不是直接觀察：
  - 26 個看板中，有 166 張卡**沒有到期日**，`dueComplete` 卻是 true。
  - 看板 actions 中，由 token 帳號以外的成員（也就是人）切換 `dueComplete` 的紀錄有 219 筆。
  - 舊版 UI 要有到期日才能勾完成，所以這些應是新的完成圈圈寫入的 → complete 沿用 `dueComplete`。
  - 直接觀察留給 5.3：使用者在 LINE 上按 ✅完成，Trello 的圈圈應該跟著變成已完成。
- ~~卡內待辦項是否繼承卡片負責人~~ → 使用者已於 2026-10-19 決定：有 due 的待辦項繼承卡片負責人，指派給公司帳號的歸公司。見 D3a。
