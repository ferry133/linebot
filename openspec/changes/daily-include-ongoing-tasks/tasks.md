## 1. 收集進行中工項（notifier）

- [ ] 1.1 `run_checks`：對「清單名含『執行中』、未完成、有 tag」的工項（card desc tag 與 checklist 皆是），emit ongoing rec 給 `set(sponsors + internal)`
- [ ] 1.2 移除舊的 `_in_summary`/±7 窗口 `summary_items` 收集（或改為不再用於進行中段）
- [ ] 1.3 ongoing rec 攜 board、卡片名、label（無 label 用卡片名）、overdue（`end < 今天`）

## 2. 呈現（build_flex 下段）

- [ ] 2.1 下段改由該收件人的 ongoing recs 呈現：依 board 分段、與上段 `upper_labels` 去重、無按鈕
- [ ] 2.2 card 層級（label==卡片名）以卡片名顯示，移除「`lb==card` 且未逾期→略過」對進行中段的作用
- [ ] 2.3 逾期（end<今天）標紅字

## 3. 驗證

- [ ] 3.1 `70. [木工] 封板`（大宅天景，執行中，`[@(木欽),0626-0715]`）出現在主管與木欽(vendor) 的今日提醒進行中段
- [ ] 3.2 結束日 >7 天的執行中工項（如木地板簽約 07/30）出現
- [ ] 3.3 已完成 / 未執行清單工項不出現在進行中段
- [ ] 3.4 廠商看到自己的進行中；非其被指派者不出現
- [ ] 3.5 與上段急迫項去重、逾期標紅；py_compile 通過

## 4. 部署

- [ ] 4.1 bump notifier + customer-service image（`scripts/bump-linebot-image.sh`）
- [ ] 4.2 部署後主管/廠商各路徑實機驗證 3.1–3.5
