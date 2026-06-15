## Context

`run_checks(mode)` 在 morning 模式下，於兩處無條件把工項收進 `summary_items`：
- [trello_line_notifier.py:379-380] 卡片描述首行解析出標記後
- [trello_line_notifier.py:395-396] checklist 工項解析出標記後

兩處都已從 `parse_tag` 取得 `start`（`date | None`）。`days_diff(d)` 回傳 `(d - today).days`。摘要 render（`build_flex` 的 `_summary_bubble`）吃的是 `summary_items` 聚合後的巢狀結構，因此只要在收集端過濾即可，render 不必動。

## Goals / Non-Goals

- 以 ±7 補出缺的端點後，摘要納入「**未完成**且 今天 ≥ 補完 start」的工項（無上界）；今天 > 補完 end 者標「逾期」（紅字）。
- 排除：已完成、未來才開始（今天 < 補完 start）、無日期者。
- 改動在 `summary_items` 收集處（加 overdue 旗標）與摘要 render（呈現逾期記號）；#1~#8 不變。

**Non-Goals:**
- 不動 #1~#8 任何通知判斷（如 #2「今日開始」仍在 start 當天發、#5/#6 逾期仍照常發）。
- 不動 completion gate、未對應 alias 警告、「已完成未歸欄」警告。
- 不另做「即將開始 N 天內才顯示」這類視窗。

## Decisions

**D1：±7 補完窗口後，以「未完成 且 今天 ≥ 補完 start」決定納入；今天 > 補完 end 標逾期。**
```python
def _summary_window(start, end):
    if start and end: return start, end
    if end:           return end - timedelta(days=7), end       # 只有 end → [end-7, end]
    if start:         return start, start + timedelta(days=7)    # 只有 start → [start, start+7]
    return None, None

def _in_summary(start, end, is_complete) -> bool:
    if is_complete:
        return False
    ns, _ = _summary_window(start, end)
    return ns is not None and days_diff(ns) <= 0     # 今天 >= 補完 start，無上界

def _summary_overdue(start, end) -> bool:
    _, ne = _summary_window(start, end)
    return ne is not None and days_diff(ne) < 0      # 今天 > 補完 end
...
if mode == "morning" and _in_summary(start, end, is_complete):
    summary_items.append((board_name, list_name, card["name"], label, _summary_overdue(start, end)))
```
- 共同前提 `not is_complete`：已打勾完成者一律不入摘要。
- ±7 補端點解決半開區間：`[@(sa),20260530-]`（只有 start）→ 補 end=start+7，今天若已過 start+7 即標逾期；`[@(bobo),-20260620]`（只有 end）→ 補 start=end-7，到期前一週即進摘要。
- 納入用「今天 ≥ 補完 start」無上界：逾期未完成持續顯示直到打勾完成。
- 逾期旗標用「今天 > 補完 end」：含只有 start／只有 end 的補完端點。
- `is_complete`／overdue 旗標在兩處 append 點皆可由 card `dueComplete` / checklist `state` 與 start/end 取得。

**D2：抽 module-level helper `_in_summary` / `_is_overdue`。**
與 `days_diff`/`_due_color` 同層的小 helper，DRY、好測。`summary_items` 加第 5 元素 `overdue` 旗標。

**D3：逾期記號在 render 呈現。**
`summary_items` 5-tuple 帶 `overdue`；摘要 tree 的 leaf 由 `label` 改為 `(label, overdue)`；render 時逾期工項以紅字 `⚠️ {label}（逾期）` 呈現（label==card 的 desc 卡則顯示 `⚠️ 逾期`）。

## Risks / Trade-offs

- [已完成工項從摘要消失] → 設計即如此：打勾完成者（含窗口內提前完成、逾期才完成）無需再佔摘要版面；未完成的窗口內／逾期工項仍保留。以 pod read-only run_checks('morning') 驗證收集集合涵蓋各情境。
- [端點/逾期判定錯位] → `days_diff` 以日期（非時間）計：`days_diff(end) >= 0` 視為未過期（end 當天仍在窗口內）、`< 0` 才算逾期，符合直覺。

## Migration Plan

純程式變更。部署：push linebot → CI → bump jg-base 全部 pin → Flux reconcile。Rollback：還原 image pin。
