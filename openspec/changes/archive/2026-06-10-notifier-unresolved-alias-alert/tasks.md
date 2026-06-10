## 1. 收集未對應 alias（per-run）

- [x] 1.1 在 `trello_line_notifier.py` 新增 module-level `_unresolved_aliases: dict[str, set[str]]`
- [x] 1.2 `run_checks()` 進入時 `_unresolved_aliases.clear()`（每次 run 重置）
- [x] 1.3 `_resolve_tag_recipients()` 簽名加 `source: str | None = None`；未對應名字時除既有 `print` 外，`setdefault(n, set())` 並在 `source` 非空時加入

## 2. 在呼叫點帶上出處

- [x] 2.1 `check_item()` 內的 `_resolve_tag_recipients(names)` 改傳 `source=f"{board_name}/{card_name}"`
- [x] 2.2 確認 `sa`／`larry` 等系統呼叫維持不傳 source（向下相容，預設 None）

## 3. morning 早報 render

- [x] 3.1 在 `run_checks()` 的 `if mode == "morning"` 區塊、基礎 summary 文字組好後，若 `_unresolved_aliases` 非空，附加「⚠️ 查無對應 LINE 帳號（未發送通知）」段落（有工項／無工項兩分支皆適用）
- [x] 3.2 每個名字後括號列出出處，超過 3 個出處時截斷為「…等 N 處」；無 source 則只列名字
- [x] 3.3 noon／evening 區塊不做任何 render（僅保留 log）

## 4. 驗證

- [x] 4.1 構造含未知 alias 的情境（或用現有 `欽`／`小千`／`上博`），跑 morning，確認早報尾端出現警告段落且帶出處 — 對現役 jg-jiahd 真實資料驗證通過，三名字去重且帶看板/卡片出處
- [x] 4.2 無未對應 alias 的情境，確認早報輸出與變更前一致（無多餘段落）— 由 `if _unresolved_aliases:` 守衛保證
- [x] 4.3 跑 noon／evening，確認對外訊息不含未對應清單、行為不變 — render 整段在 `if mode == "morning"` 內，結構上保證
