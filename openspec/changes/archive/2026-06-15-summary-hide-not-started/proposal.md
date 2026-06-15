## Why

每日工程摘要（#9）目前把所有帶 `[@...]` 標記的工項全列出，完全不看日期。導致開始日還在數月後的工項（例如九月才開始的「B 室裝檢查」）也出現在今天的摘要中，造成雜訊、混淆「現在該關注什麼」。

## What Changes

- 每日摘要（morning #9）SHALL 先以 **±7 天**補完半開區間（只有 end→`[end-7,end]`、只有 start→`[start,start+7]`），再納入**尚未完成**且 **今天 ≥ 補完 start** 的工項（無上界）。
- 凡 **今天 > 補完 end** 的工項在摘要中 SHALL 標示「逾期」記號（紅字）。
- 排除：**已完成**、**未來才開始**（今天 < 補完 start）、以及**完全沒設日期**者。
- 僅影響 morning 摘要的 `summary_items` 收集與呈現；#1~#8 的通知判斷（含 #5/#6 逾期通知）與既有的 completion gate、未對應 alias 警告、「已完成未歸欄」警告 MUST 維持不變。

## Capabilities

### New Capabilities

- `notification-daily-summary`: 定義每日工程摘要（#9）納入哪些工項——以 ±7 補完窗口後，**未完成**且 今天 ≥ 補完 start 者納入，今天 > 補完 end 者標「逾期」；已完成、未來才開始、無日期者排除。

### Modified Capabilities

（無）

## Impact

- 程式：`trello_line_notifier.py` 新增 `_in_summary` / `_is_overdue`；兩處 `summary_items.append(...)` 加 overdue 旗標（5-tuple）；摘要 render 呈現逾期紅字記號。
- 文件：`trello-line-design.md` #9 列說明補上納入規則與逾期記號。
- 行為：摘要只反映「尚未完成」且今天 > start 或 > end 的工項，逾期者標紅；已完成、未到期的只有 end、未來工項不入摘要。無 DB／schema 變更。
