## 1. 程式

- [x] 1.1 新增 `_summary_window(start, end)`（±7 補半開區間）、`_in_summary`（未完成且 今天≥補完start）、`_summary_overdue`（今天>補完end）。
- [x] 1.2 兩處 `summary_items.append(...)` 5-tuple，overdue 旗標用 `_summary_overdue(start, end)`；`is_complete` 閘控。
- [x] 1.3 摘要 render：tree leaf `(label, overdue)`；逾期工項紅字 `⚠️ {label}（逾期）`（label==card 顯示 `⚠️ 逾期`）。

## 2. 文件

- [x] 2.1 `trello-line-design.md` #9 列與前言補上 ±7 補完窗口規則與逾期紅字記號。

## 3. 驗證

- [x] 3.1 `ast.parse` 通過；本機 truth table（含兩實際案例：#2收款只有start標逾期、各工種委任只有end到期前一週顯示）全 PASS。
- [x] 3.2 部署後 pod 內 read-only 驗證：大宅天景「#2.工程約第2次收款」標逾期；創世紀M3「02.各工種委任工程約」出現；B室裝檢查仍隱藏。
- [x] 3.3 試發摘要給 larryoffice only，確認兩案例與逾期紅字呈現正確。

## 4. 上線

- [x] 4.1 commit + push linebot；CI build。
- [x] 4.2 bump jg-base 全部 image pin → Flux reconcile。
