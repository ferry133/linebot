## Why

`trello_line_notifier.py` 的 `_resolve_tag_recipients()` 在 Trello 標記用到的名字（`@(欽)`、`@(小千)`、`@(上博)`…）於 `line_users.alias_name` 查無對應時，只 `print` 一行 log warning 就略過 —— 被標記的人**靜默漏收通知**，而 SA/Larry 永遠不會發現（與 NAS 知識庫權限同類的 silent failure）。需要把這個訊號從沒人看的 pod log，搬到 SA/Larry 每天會看的地方。

## What Changes

- 在一次 notifier run 期間**收集**所有查無對應的 alias 名字（去重，理想帶上出處：看板／卡片）。
- 在 morning `#9` 每日摘要（本來就發給 SA/Larry）**尾端附加**一段「⚠️ 查無對應 LINE 帳號」清單，列出當次漏接的名字。
- 無漏接時不顯示該段（摘要維持原樣）。
- 範圍限定：**只併進每日早報**。不另推管理群組、不做 admin UI、不改 noon/evening 行為。
- 不改 DB schema、不加環境變數；既有 `print` log 警告可保留。

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `contacts-integration`: 新增需求 —— alias 解析失敗時，系統必須將未對應的名字呈現給營運者（透過 morning 每日摘要），不可僅停留在 log。

## Impact

- **程式**：`trello_line_notifier.py`
  - `_resolve_tag_recipients()`：把未對應 alias 累積到一個 per-run 收集器（而非只 print）。
  - `run_checks()` 的 morning `#9` 摘要組裝：若收集器非空，附加警告段落。
- **行為**：morning 摘要訊息內容在有漏接時會多一段；noon／evening 不變。
- **無**：DB schema 變更、環境變數、外部 API、相依套件。
