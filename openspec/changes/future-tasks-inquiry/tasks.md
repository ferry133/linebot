## 1. 區間收集器（notifier）

- [x] 1.1 `build_future_messages_for_user(user_id, role, direction="future", window="1m")`：window→天數 {2w:14,1m:30,2m:60,3m:90};區間 future=[今天,今天+n]、past=[今天-n,今天]
- [x] 1.2 `_scan_boards()` 掃描 → 未完成、有 `[@]` tag、start 或 end 落在區間 → 產「開始」/「到期」事件（同工項可各一）
- [x] 1.3 RBAC 過濾（supervisor 全部 / vendor 自身 alias / customer 其看板）；public_label 去 PII
- [x] 1.4 依事件日期升序；Flex 依日期分組（日期抬頭 + `開始/到期 · public_label · 卡片/label`）；唯讀、附「依目前進度推算」
- [x] 1.5 quick-reply：未來(2週/1月/2月/3月)+ 過去(2週/1月/2月/3月)+「📅 指定日期」(datetimepicker o=someday)
- [x] 1.6 空區間回「(方向 視窗) 內無工項」+ quick-reply；筆數上限保護

## 2. 路由（customer_service）

- [x] 2.1 `_process_postback`：`o=future` 讀 `dir`(f/p)/`n` → `_handle_future(user_id, reply_token, direction, window)`；缺/非法回退未來1月
- [x] 2.2 `_handle_future` 呼叫 `build_future_messages_for_user` 並經 OUTBOX Reply
- [x] 2.3 「📅 指定日期」quick-reply 仍走既有 `o=someday`（不動 someday 引擎）

## 3. Rich Menu

- [x] 3.1 `setup_richmenu.py`：中間格 label「未來工項」、action `postback o=future`；重繪底圖（時間軸/月曆圖示）
- [ ] 3.2 `--preview` 出圖確認後，安全序部署（建新+設預設→刪舊）

## 4. 驗證

- [x] 4.1 未來1月/3月、過去2週 各列出正確區間工項、依日期排序、標開始/到期
- [x] 4.2 vendor 只見自己、customer 只見其看板、supervisor 全部；唯讀無完成鈕；含推算註記
- [x] 4.3 quick-reply 切換視窗/方向正確；「指定日期」仍進 someday 單日
- [x] 4.4 空區間訊息 + 參數非法回退；py_compile 通過

## 5. 部署

- [ ] 5.1 bump image（gateway + customer-service + notifier 同 image）
- [ ] 5.2 部署後實機：Rich Menu「未來工項」→ 區間清單 + quick-reply；指定日期 → someday
