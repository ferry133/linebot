## Context

現況「其餘進行中」下段來自 `run_checks` 的 `summary_items`（`_in_summary`：未完成且今天 ≥ ±7 補完窗口起點），只發 internal，且 `build_flex` 下段有「`lb==card` 且未逾期→略過」規則。兩者導致：結束日 >7 天的進行中工項被窗口排除；card 層級無 label 的（如 `70.封板 [@(木欽),0626-0715]`）被略過。使用者要「執行中清單、未完成」全列，且主管+廠商都看。

## Goals / Non-Goals

**Goals:** 進行中段＝執行中清單、未完成、有 tag（不論日期）；card 層級以卡片名顯示；主管＋被 tag 的廠商都看。
**Non-Goals:** 不改 #1–#8 觸發、確認卡、警告、RBAC；不改「未執行/已完成」清單（不列入進行中段）。

## Decisions

**1. 收集改「清單導向 + per-recipient」**
`run_checks` 掃描時，對「清單名含『執行中』、未完成、有 `[@(alias)]` tag」的工項，emit 一筆 **ongoing rec** 給 `set(sponsors + internal)`（取代僅 internal、以 `_in_summary`/±7 窗口收集的 `summary_items`）。ongoing rec 攜 board、卡片名、label、overdue（`end < 今天`）。card desc tag 與 checklist 工項皆適用。
- 廠商因此看到自己的進行中（sponsors 含被 tag 的 vendor）；主管看到其可見範圍內全部（internal）。

**2. `build_flex` 下段改由 ongoing recs 呈現**
下段依 board 分段、與上段 `upper_labels` 去重、無按鈕；**card 層級（label 預設為卡片名）以卡片名顯示**，移除「`lb==card` 且未逾期→略過」對進行中段的作用。逾期者標紅。清單分欄可簡化為單一「進行中工項」段（只剩執行中）。

**3. 「執行中」判定**
以清單名 `includes("執行中")` 判定（與既有 `_status_color` 同慣例）。

## Risks / Trade-offs

- [廠商 push 內容/額度增加] → 使用者已同意（主管+廠商）。
- [一卡多工項的去重] → 以 `(卡片名, label)` 為鍵，與上段 `upper_labels` 一致比對。
- [大量進行中 → carousel 12 上限] → 沿用截斷；確認卡優先仍在最前。
