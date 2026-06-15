## Context

`run_checks(mode)` 在 morning 模式下，於兩處無條件把工項收進 `summary_items`：
- [trello_line_notifier.py:379-380] 卡片描述首行解析出標記後
- [trello_line_notifier.py:395-396] checklist 工項解析出標記後

兩處都已從 `parse_tag` 取得 `start`（`date | None`）。`days_diff(d)` 回傳 `(d - today).days`。摘要 render（`build_flex` 的 `_summary_bubble`）吃的是 `summary_items` 聚合後的巢狀結構，因此只要在收集端過濾即可，render 不必動。

## Goals / Non-Goals

- 摘要納入「**未完成**且（窗口內 或 逾期）」的工項：窗口內＝`start`、`end` 皆有且 `start <= 今天 <= end`；逾期＝有 `end` 且 `今天 > end`（`start` 可選）。
- 排除：已完成（不論窗口內或逾期）、未來才開始、只有 `end` 但未到期、只有 `start` 無 `end`、無日期者。
- 改動侷限在 `summary_items` 收集處；其餘行為不變。

**Non-Goals:**
- 不動 #1~#8 任何通知判斷（如 #2「今日開始」仍在 start 當天發、#5/#6 逾期仍照常發）。
- 不動 completion gate、未對應 alias 警告、「已完成未歸欄」警告。
- 不另做「即將開始 N 天內才顯示」這類視窗。

## Decisions

**D1：以「未完成 且（窗口內 或 逾期）」決定是否納入摘要。**
```python
def _in_summary(start, end, is_complete) -> bool:
    if is_complete:
        return False
    in_window = bool(start) and bool(end) and days_diff(start) <= 0 <= days_diff(end)
    overdue = bool(end) and days_diff(end) < 0
    return in_window or overdue
...
if mode == "morning" and _in_summary(start, end, is_complete):
    summary_items.append((board_name, list_name, card["name"], label))
```
- 共同前提 `not is_complete`：已打勾完成者一律不入摘要（不論窗口內或逾期）。
- `in_window`：要有完整 `start`/`end`，今天落在 `[start, end]`（含端點）。排除未來才開始、只有 end 未到期、只有 start 無 end。
- `overdue`：只要有 `end` 且今天已過 `end` 即可（`start` 不要求），故「只有 end 的逾期未完成」也涵蓋。
- `is_complete` 在兩處 append 點皆可取得：card `dueComplete` / checklist `state`。
- 對照使用者的決策表（最先符合者優先）：overdue 子句先攔「只有 end 的逾期未完成」，故「缺 start/end → ❌」只作用於未被前面攔到的剩餘情況（只有 start、只有 end 未到期、無日期），二者一致。

**D2：抽 module-level helper `_in_summary(start, end, is_complete)`。**
條件含 3 行布林、且在卡片描述／checklist 兩處重複，抽成與 `days_diff`/`_due_color` 同層的小 helper 較 DRY、好測，並與既有 module-level helper 風格一致。

## Risks / Trade-offs

- [已完成工項從摘要消失] → 設計即如此：打勾完成者（含窗口內提前完成、逾期才完成）無需再佔摘要版面；未完成的窗口內／逾期工項仍保留。以 pod read-only run_checks('morning') 驗證收集集合涵蓋各情境。
- [端點/逾期判定錯位] → `days_diff` 以日期（非時間）計：`days_diff(end) >= 0` 視為未過期（end 當天仍在窗口內）、`< 0` 才算逾期，符合直覺。

## Migration Plan

純程式變更。部署：push linebot → CI → bump jg-base 全部 pin → Flux reconcile。Rollback：還原 image pin。
