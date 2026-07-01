## Context

下段「其餘進行中」來自 `run_checks` 的 `summary_items`（`_in_summary`：未完成且今天 ≥ ±7 補完窗口起點、逾期續顯示），**此窗口判定正確、保留**。缺口有二：(1) `build_flex` 下段「`lb==card` 且未逾期→略過」把 card 層級無 label 的窗口內工項（如 `70.封板 [@(木欽),0626-0715]`）吃掉；(2) `summary_items` 只發 internal，廠商看不到自己的進行中。

## Goals / Non-Goals

**Goals:** 修呈現略過（card 層級以卡片名顯示）；下段對象擴及被 tag 的 vendor。
**Non-Goals:** **不改 ±7 補完窗口的納入/逾期判定**；不改 #1–#8 觸發、確認卡、警告、RBAC。

## Decisions

**1. 保留窗口判定，改為 per-recipient 發送**
沿用 `_in_summary`/`_summary_window`/`_summary_overdue`（±7 補完）判斷工項是否在進行中。原本 `summary_items` 收進單一 internal 摘要 → 改為對每個在窗口內的工項，emit 進行中 rec 給 `set(sponsors + internal)`：主管（internal）看其可見範圍全部、廠商（被 tag 的 sponsor）看自己的。card desc tag 與 checklist 工項皆適用。

**2. `build_flex` 下段呈現**
下段依 board 分段、與上段 `upper_labels` 去重、無按鈕、逾期標紅（皆不變）；**移除「`lb==card` 且未逾期→略過」**，改為 card 層級（label 預設為卡片名）以**卡片名**呈現，使 `70.封板` 類工項顯示。

## Risks / Trade-offs

- [廠商 push 內容/額度增加] → 使用者已同意（主管+廠商）。
- [移除略過規則可能讓「label 恰等於卡片名」的正常工項也列出] → 這正是預期（它們本就是窗口內未完成工項，應顯示）；仍以 `(卡片名, label)` 對上段去重避免重複。
- [大量進行中 → carousel 12 上限] → 沿用截斷；確認卡優先仍在最前。
