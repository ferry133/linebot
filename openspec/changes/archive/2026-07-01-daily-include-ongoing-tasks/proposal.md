## Why

今日提醒的「其餘進行中」下段沿用 ±7 補完窗口判斷「今天是否在進行中」（未完成且今天 ≥ 補完後起點；逾期續顯示）——**此判斷正確、保留不動**。但仍有兩個缺口讓進行中工項看不到：

1. **呈現略過**：`70. [木工] 封板`（大宅天景，`[@(木欽),20260626-20260715]`）今天（07/01）明明在補完窗口內（06/26 ≤ 今天 ≤ 07/15），卻不顯示——因 build_flex 下段有「`label 等於卡片名` 且未逾期 → 略過」規則，而此卡 tag 未填 label（預設成卡片名）而被吃掉。
2. **對象太窄**：下段「其餘進行中」僅呈現給主管；廠商看不到自己的進行中工項（只收急迫項）。

## What Changes

- **保留** ±7 補完窗口的納入/逾期判斷（`_in_summary`：未完成且今天 ≥ 補完後 `start`，今天 > 補完後 `end` 標逾期）。缺開始→`[end−7,end]`、缺結束→`[start,start+7]`、皆有→`[start,end]`。**不改。**
- **修呈現略過規則**：card 層級（tag 未填 label，label 預設為卡片名）且在窗口內的進行中工項 SHALL 以**卡片名**呈現，MUST NOT 因「label 等於卡片名且未逾期」而被略過。
- **對象擴及廠商**：下段「其餘進行中」除主管外，亦呈現給該工項被 `[@(alias)]` 標記的 vendor（僅自己被指派、且在補完窗口內者）。仍與上段去重、標逾期、無按鈕。

## Capabilities

### Modified Capabilities
- `notification-daily-summary`: 合併卡片下段修正 card 層級無 label 被略過；下段對象由「僅主管」擴及被 tag 的 vendor。**±7 補完窗口納入/逾期規則不變。**
- `consolidated-daily-notification`: vendor 每日內容除急迫觸發項外，亦含其被 tag、在補完窗口內、未完成的進行中工項。

## Impact

- `trello_line_notifier.py`：進行中工項（沿用 `_in_summary` 窗口判定）改以 per-recipient 發給 `sponsors + internal`（原僅 internal），使廠商也收到自己的；`build_flex` 下段移除「`lb==card` 且未逾期→略過」、card 層級以卡片名顯示。
- 影響 vendor push 內容量（使用者已同意）；不影響 ±7 窗口納入判定、#1–#8 觸發、確認卡、警告、RBAC。
