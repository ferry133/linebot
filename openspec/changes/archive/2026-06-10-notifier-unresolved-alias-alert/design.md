## Context

`trello_line_notifier.py` 以 one-shot CronJob 形式執行（morning/noon/evening）。alias→line_id 解析集中在 `_resolve_tag_recipients(names)`：對每個查無對應的名字 `print` 一行 `[notifier] WARNING: alias not found: <n>` 即略過。此函式主要被 `check_item()`（line ~263，握有 `board_name`／`card_name` 上下文）呼叫；另被固定的 `sa`／`larry` 系統收件人解析呼叫（這些通常已註冊，少有未對應）。

morning `#9` 每日摘要在 `run_checks()` 末段（`if mode == "morning"`）組裝，產生一則 `__summary__` 通知發給 SA/Larry：有工項時為「📋 每日工程摘要…」，無工項時為「📋 今日無進行中工項」。

## Goals / Non-Goals

**Goals:**
- 把「未對應 alias」從 log 提升為 SA/Larry 每天早報可見的內容。
- 去重；理想帶上出處（看板／卡片），讓 Larry 知道去哪補。
- 無漏接時早報輸出與現狀**完全一致**（不產生空段落）。
- 不改 DB schema、不加環境變數、不動 noon/evening 對外行為。

**Non-Goals:**
- 不推管理群組、不做 admin UI（已由使用者選定只走早報）。
- 不改變實際的收件人解析結果或發送邏輯（只新增「呈現」）。
- 不移除既有的 `print` log 警告（保留供 log 追蹤）。

## Decisions

### D1. Per-run 收集器：module-level dict，run 開始時重置
新增 module-level `_unresolved_aliases: dict[str, set[str]]`（name → 出處集合）。`run_checks()` 進入時 `clear()`。
- 理由：解析散落在多處呼叫，集中收集最簡單；CronJob 雖每次都是新行程，仍明確重置以利測試與避免任何殘留。

### D2. 在 `_resolve_tag_recipients` 收集，並加可選 `source` 帶上下文
簽名改為 `_resolve_tag_recipients(names, source: str | None = None)`：
- 未對應名字時，除既有 `print` 外，`_unresolved_aliases.setdefault(n, set())`，若 `source` 非空則加入。
- `check_item()` 的呼叫傳 `source=f"{board_name}/{card_name}"`；`sa`／`larry` 等系統呼叫不傳 source（預設 None）。
- 理由：在唯一解析點收集，零重複；optional 參數對既有呼叫向下相容。

### D3. 只在 morning `#9` 末段 render
在 `run_checks()` 組好基礎 summary 文字後（兩個分支：有工項／無工項皆適用），若 `_unresolved_aliases` 非空，附加一段：
```
⚠️ 查無對應 LINE 帳號（未發送通知）
・欽（板A/卡1）
・小千（板B/卡3）
・上博
```
- 名字後括號列出出處（最多列 N 個，避免過長；無 source 則只列名字）。
- 附加到 `summary` 字串後再 append 進 notifications（沿用既有 `__summary__` 流程與 `build_flex` 的 summary 分支）。
- 理由：morning 摘要是既有、發給 SA/Larry 的單一出口，附加最小侵入。

### D4. noon/evening 不 render
render 僅在 `if mode == "morning"` 區塊內；noon/evening 即使收集器有內容也不輸出面向使用者的清單（仍有 log）。符合 spec scenario「非 morning 時段不改變行為」。

## Risks / Trade-offs

- **出處可能很多**：同一個未知名字若出現在多張卡片，出處集合會變大 → render 時截斷（例如最多 3 個，超過顯示「…等 N 處」），避免訊息過長。
- **module-level 可變狀態**：在長駐行程會跨呼叫累積，但 notifier 是 one-shot；以 D1 的 run 起始 `clear()` 消除風險，並讓單元測試可重置。
- **sa/larry 未註冊的邊界**：若連 `sa`／`larry` 都查無對應（理論上不該發生），會以無 source 形式列入清單 —— 這其實是有用的告警，不視為問題。
- **僅早上才知道**：使用者已接受此取捨（一天一次、in-band）；未來要即時或可操作化，可再加 B（群組推播）或 C（admin UI），與本設計不衝突。
