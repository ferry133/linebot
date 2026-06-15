## 1. 程式

- [x] 1.1 新增 module-level helper `_in_summary(start, end, is_complete)`（未完成且 窗口內或逾期）；卡片描述分支以 `is_complete = bool(card.get("dueComplete"))`，僅在 `mode == "morning" and _in_summary(start, end, is_complete)` 時 append。
- [x] 1.2 checklist 工項分支套用相同 `_in_summary` 閘控，`is_complete = (item.get("state") == "complete")`。

## 2. 文件

- [x] 2.1 `trello-line-design.md` #9 列訊息內容補上「僅含今天落在完整 `[start,end]` 區間內的工項（缺端點／未來／逾期者不列入）」。

## 3. 驗證

- [x] 3.1 `ast.parse` 通過；本機 stub 驗證：窗口內未完成→納入、窗口內已完成→排除、逾期未完成(含只有 end)→納入、逾期已完成→排除、未來(today<start)→排除、只有 start／只有 end未到期／無日期→排除。
- [ ] 3.2 部署後 pod 內 read-only `run_checks('morning')`，確認「B 室裝檢查」等未來工項不在摘要 summary_items，當日/已開始工項仍在。

## 4. 上線

- [ ] 4.1 commit + push linebot；CI build。
- [ ] 4.2 bump jg-base 全部 image pin → Flux reconcile。
