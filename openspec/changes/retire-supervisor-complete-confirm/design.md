## Context

#16 已讓 `build_flex(show_buttons=)` 依角色顯示完成按鈕：vendor/customer 有、admin/employee 無（已上線 9803392）。先前 merge-daily 案為主管完成加的「方案3 二次確認」（`o=complete`+supervisor → 回 [是][否] → `o=complete_confirm` 才寫）因此失去觸發點。本案清掉它並對齊 spec。

## Goals / Non-Goals

**Goals:** 移除多餘的方案3（路由/gate/flex）；spec 反映「完成鈕單顆且僅 vendor/customer」。
**Non-Goals:** 不動顯示層（#16 已上線）、不動廠商一鍵暫定、不動「待主管確認」核可（確認/退回）。

## Decisions

**1. 直接移除方案3，不保留 stale-card 防呆**
雖然舊卡片（部署前發出）理論上仍可能讓主管點到 `o=complete`，但：移除 gate 後，主管若點到舊卡 `o=complete`，會走一般 owner/supervisor 驗證後直接定案——對主管而言本來就是合法操作（只是少了確認）。風險極低（舊卡很快過期/被新卡取代），不值得保留兩條 op 與兩個 flex 方法的複雜度。`complete = (op == "complete")` 還原。

**2. `complete_cancel` 一併移除**
僅服務方案3 的「否」，無其他用途。

## Risks / Trade-offs

- [舊卡片主管點完成 → 直接定案、無確認] → 主管定案本為合法；舊卡短命；可接受。
- [若日後又想給主管完成鈕] → 屆時用 #16 的 `show_buttons` 開關即可；二次確認另議。
