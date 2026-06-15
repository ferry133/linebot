## 1. 程式

- [x] 1.1 新增 module-level helper `_is_overdue(end)`（今天 > end）與 `_in_summary(start, end, is_complete)`（未完成且 今天>start 或 今天>end）。
- [x] 1.2 兩處 `summary_items.append(...)`（卡片描述 + checklist）改 5-tuple，加 `_is_overdue(end)` overdue 旗標；以 `is_complete`（card `dueComplete` / checklist `state`）閘控。
- [x] 1.3 摘要 render：tree leaf 改為 `(label, overdue)`；逾期工項以紅字 `⚠️ {label}（逾期）` 呈現（label==card 的 desc 卡顯示 `⚠️ 逾期`）。

## 2. 文件

- [x] 2.1 `trello-line-design.md` #9 列與前言補上納入規則（今天>start 或 今天>end；逾期標紅）。

## 3. 驗證

- [x] 3.1 `ast.parse` 通過；本機 stub 驗證 11 種情境（含逾期標記）show/overdue 全 PASS。
- [ ] 3.2 部署後 pod 內 read-only `run_checks('morning')`，確認未來工項（B 室裝檢查）不在摘要、逾期工項帶逾期旗標。
- [ ] 3.3 試發摘要給 larryoffice only，確認逾期紅字記號呈現正確。

## 4. 上線

- [ ] 4.1 commit + push linebot；CI build。
- [ ] 4.2 bump jg-base 全部 image pin → Flux reconcile。
