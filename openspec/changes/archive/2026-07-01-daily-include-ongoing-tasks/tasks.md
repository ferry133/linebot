## 1. per-recipient 進行中收集（notifier，保留窗口判定）

- [x] 1.1 沿用 `_in_summary`/`_summary_window`/`_summary_overdue`（±7 補完窗口）判定進行中，**不改**
- [x] 1.2 `run_checks`：對每個在窗口內的進行中工項，emit rec 給 `set(sponsors + internal)`（取代僅 internal 的單一 `summary_items`）
- [x] 1.3 rec 攜 board、卡片名、label（無 label 用卡片名）、overdue

## 2. 呈現（build_flex 下段）

- [x] 2.1 移除下段「`lb==card` 且未逾期→略過」規則，card 層級以卡片名顯示
- [x] 2.2 下段依收件人 recs 呈現：依 board 分段、與上段 `upper_labels` 去重、逾期標紅、無按鈕（不變）
- [x] 2.3 廠商下段僅含自己被 tag 的窗口內工項

## 3. 驗證

- [x] 3.1 `70. [木工] 封板`（`[@(木欽),0626-0715]`，今日在窗口內）出現在主管與木欽(vendor) 的今日提醒下段
- [x] 3.2 未進窗口的未來工項（如只有 end 07/30、今日早於 07/23）仍不出現
- [x] 3.3 已完成工項不出現；逾期標紅
- [x] 3.4 廠商看到自己窗口內進行中；非其被指派者不出現
- [x] 3.5 與上段急迫項去重；py_compile 通過

## 4. 部署

- [x] 4.1 bump notifier + customer-service image（`scripts/bump-linebot-image.sh`）
- [x] 4.2 部署後主管/廠商各路徑實機驗證 3.1–3.5
