## Why

兩個每日內容的痛點：
1. **完成按鈕易誤觸且不可逆**：提醒卡的單顆 ✅完成 一點即寫 Trello，且已無 in-LINE 還原。主管的標記是**定案**（不像廠商是暫定可退回），誤觸代價最高。
2. **主管端兩種呈現重疊**：合併為單一每日後，主管每看板同時收到「今日專案提醒」(#1–#8 可操作) 與「每日工程摘要」(#9 全覽) 兩張 bubble，同一張到期卡重複出現。

## What Changes

- **①完成防誤觸（角色分流）**：
  - **廠商**維持一鍵標記（暫定生效、主管可退回＝已有安全網）。
  - **主管**點「完成」改為**二次確認**：先回「確定將『X』標記完成？[是][否]」，僅按[是]才執行定案寫入。MUST NOT 在第一下就寫入。
- **②合併呈現（每看板單一 bubble）**：主管每看板由「提醒 bubble ＋ 摘要 bubble」合併為**單一 bubble**：
  - 上段＝今日急迫/可操作工項（#1–#8，含 ✅完成 按鈕、彩色急迫度）。
  - 下段＝該看板其餘進行中工項（#9 補完窗口內、**去重**已在上段者、標逾期、無按鈕）。
  - 不再有獨立「每日工程摘要」bubble。**廠商不受影響**（本就只有提醒、無摘要）。
  - 副作用：每看板 2→1 bubble，carousel 12 張上限更不易撞。

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `trello-task-status-update`: 主管「完成」定案前 SHALL 二次確認；廠商一鍵暫定不變。
- `notification-daily-summary`: 摘要內容改與該看板 #1–#8 提醒**合併為每看板單一卡片**（上急迫含按鈕、下其餘去重），不再獨立成 bubble。

## Impact

- `agents/customer_service.py`：`_handle_status_update` 角色分流——主管 `o=complete` → 回確認提示（[是]=`o=complete_confirm` 帶原 b/c/i/s、[否]=取消），新增 `complete_confirm` 定案分支；越權/冪等驗證在定案步驟照舊。廠商分支不變。
- `trello_line_notifier.py`：`run_checks`/`build_flex` 每看板把工項提醒與摘要窗口工項合併為單一 bubble（去重）；移除獨立 summary bubble 呈現。`__summary__` 改為 per-board section 併入。
- 不影響 RBAC（vendor tag-only）、推播額度、確認卡(待主管追認)流程。
