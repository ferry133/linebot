## Why

今日提醒目前只醒目呈現**日期觸發**的工項（今日/7 天內/逾期）。真正**進行中**（「執行中」清單、未完成）但日期不在 7 天內的工項**完全看不到**：
- `70. [木工] 封板`（大宅天景，執行中，`[@(木欽),20260626-20260715]`）在窗口內卻不顯示——因 build_flex 下段有「label 等於卡片名且未逾期→略過」規則，而此卡 tag 未填 label（預設成卡片名）而被略過。
- `木地板簽約`（end 07/30）等結束日 >7 天者，被 ±7 補完窗口排除。

使用者要看到所有**進行中**工項，不只急迫的。

## What Changes

- **「進行中工項」段納入條件改為清單導向**：工項在名稱含「執行中」的清單、**未完成**（card `dueComplete` 否／checklist `state` 非 complete）、且有 `[@(alias)]` 標記 → 列入下段，**不論日期**（取代原 ±7 補完窗口）。逾期（end < 今天）者仍標「逾期」紅字。
- **修掉略過規則**：card 層級（tag 未填 label）的進行中工項改以**卡片名**呈現，不再因 `label==卡片名` 而消失。
- **對象擴及廠商**：進行中工項段呈現給 **supervisor（全部）＋ 該工項被 tag 的 vendor（自己的）**（原本僅 supervisor）。仍與上段急迫項去重、無按鈕。

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `notification-daily-summary`: 「其餘進行中」段納入條件由 ±7 補完窗口改為「執行中清單、未完成」（不論日期）；修正 card 層級無 label 被略過；呈現對象擴及被 tag 的 vendor。
- `consolidated-daily-notification`: vendor 的每日內容除急迫觸發項外，亦含其被 tag 的進行中（執行中、未完成）工項。

## Impact

- `trello_line_notifier.py`：`run_checks` 以「執行中清單 + 未完成 + 有 tag」收集進行中工項，發給 `sponsors + internal`（取代僅 internal 的 ±7 窗口 `summary_items`）；`build_flex` 下段改由這些 rec 呈現、去重上段、card 層級以卡片名顯示、逾期標紅。
- 影響 vendor push 內容量（使用者已同意）；不影響 #1–#8 觸發、確認卡、警告、RBAC。
