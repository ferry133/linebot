## Context

合併三批次後（image 88a5418+），主管每日內容/拉取包含：每看板「提醒 bubble(#1–#8 + ✅完成)」+「摘要 bubble(#9 狀態樹)」兩張，重疊；且 ✅完成 單顆一點即寫、已無 in-LINE 還原（取消完成按鈕先前移除）。廠商只收提醒(暫定、主管可退回)。本案：主管完成二次確認(方案3) + 每看板合併單一卡片(方案C)。

## Goals / Non-Goals

**Goals:** 主管不可逆「完成」前先確認；主管每看板提醒+摘要合併為一張卡。
**Non-Goals:** 不改廠商一鍵暫定、不改 #1–#8 觸發與摘要納入規則、不改確認卡(待主管追認)流程、不改 RBAC/額度。

## Decisions

**1. 二次確認在「點按時依角色」決定，按鈕本身不變**
維持卡上單顆「✅完成」(`o=complete`)。`_handle_status_update`：
- `op=complete` + 廠商(owner 非 supervisor) → 既有暫定路徑（一鍵）。
- `op=complete` + supervisor → **不寫**，回確認提示：是=`o=complete_confirm&b&c&i&s`、否=純 displayText 取消。
- `op=complete_confirm` + supervisor → 定案寫入（現行 supervisor 分支）；重讀卡片驗 owner/supervisor + allowed_board_ids + 冪等。
確認提示走 Reply API（免費）。避免在每張卡放兩顆按鈕（版面/誤觸）。

**2. 每看板合併：摘要由「全域單一 rec」改為「per-board 區段」**
現況 `run_checks` 產一個全域 `__summary__` rec（含所有看板樹）。改為：摘要工項依 board 分組，於 `build_flex` 時併入該看板的提醒 bubble 下段；上段＝該看板 item recs(#1–#8)。去重：下段排除「raw/工項已在上段」者（以 card+label 或 raw 比對）。
- vendor：無摘要 rec → 只有上段（現狀）。
- 空看板不出 bubble；標頭用 public_label。
- 「待主管確認」確認卡與 warnings 仍為獨立 bubble。

## Risks / Trade-offs

- [合併 bubble 變長] → 單 bubble 內可捲動；每看板 2→1 反而更省 carousel 12 張額度。
- [去重比對] → 以 (card_name, label) 或 raw 字串比對；邊界（同卡多工項）需測。
- [主管多一步] → 僅作用於不可逆的主管定案；廠商與一般查詢無摩擦。
- [confirm prompt token 過期] → 屬使用者主動點按、即時回覆，窗口內；逾時 fallback push（line-message-delivery 既有行為）。
