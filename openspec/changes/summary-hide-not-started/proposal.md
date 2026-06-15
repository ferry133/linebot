## Why

每日工程摘要（#9）目前把所有帶 `[@...]` 標記的工項全列出，完全不看日期。導致開始日還在數月後的工項（例如九月才開始的「B 室裝檢查」）也出現在今天的摘要中，造成雜訊、混淆「現在該關注什麼」。

## What Changes

- 每日摘要（morning #9）SHALL 僅納入**尚未完成**且符合下列任一者：
  - **窗口內**：有 `start` 且有 `end`，且 `start <= 今天 <= end`。
  - **逾期**：有 `end`，且 `今天 > end`（`start` 可有可無，含只有 `end` 者）。
- 排除：**已完成**（不論窗口內或逾期，打勾即不顯示）、**未來才開始**（`今天 < start`）、**只有 `end` 但尚未到期**、**只有 `start` 無 `end`**、以及**完全沒設日期**者。
- 僅影響 morning 摘要的 `summary_items` 收集；#1~#8 的通知判斷（含 #5/#6 逾期通知）與既有的 completion gate、未對應 alias 警告、「已完成未歸欄」警告 MUST 維持不變。

## Capabilities

### New Capabilities

- `notification-daily-summary`: 定義每日工程摘要（#9）納入哪些工項——**未完成**且（今天落在 `[start, end]` 內 或 有 `end` 且逾期）者納入；已完成、未來才開始、只有 end 未到期、只有 start、無日期者排除。

### Modified Capabilities

（無）

## Impact

- 程式：`trello_line_notifier.py` `run_checks()` 內兩處 `summary_items.append(...)`（卡片描述 + checklist 工項），各加一道「未完成 且（窗口內 或 逾期）」判斷（用已有的 `is_complete`）。
- 文件：`trello-line-design.md` #9 列說明補上納入規則。
- 行為：摘要只反映「尚未完成」且今天在窗口內、或已逾期（含只有 end）的工項；已完成、未到期的只有 end、未來工項不入摘要。無 DB／schema 變更。
