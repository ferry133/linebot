## 1. 主管完成二次確認（方案3）

- [x] 1.1 `_process_postback` 路由新增 `complete_confirm`（+ `complete_cancel` 回「已取消」）
- [x] 1.2 `_handle_status_update`：`op=complete` + supervisor → 不寫，回確認提示（是=`o=complete_confirm&b&c&i&s`、否=`complete_cancel`）；廠商分支不變
- [x] 1.3 `complete_confirm` 經 `complete = op in (complete, complete_confirm)` 走既有 supervisor 定案寫入；owner/supervisor + allowed_board_ids + 冪等驗證照舊
- [x] 1.4 確認提示 `_complete_confirm_flex` 用 Flex 按鈕，經 reply token 回覆（免費）

## 2. 每看板合併單一卡片（方案C）

- [x] 2.1 摘要 sections 本就 per-board（board=public_label）；於 `build_flex` 以 `summary_by_board` 併入各看板（免改 run_checks 結構，結果一致）
- [x] 2.2 `build_flex`：每看板一張 bubble＝上段 #1–#8 提醒(含按鈕) + 下段「其餘進行中工項」
- [x] 2.3 去重：item rec 加 `label`(rec[9])；下段排除 `(card, label)` 已在上段者（拆除磁磚 dedup 驗證為 1 次）
- [x] 2.4 移除獨立摘要 bubble；空看板不出（`if not body: continue`）；標頭 `意念情境・今日工程` + public_label
- [x] 2.5 廠商不受影響（無 summary rec → 僅上段）；確認卡與 warnings 仍獨立 bubble

## 3. 驗證

- [x] 3.0 本機單元：合併一張 bubble（上含按鈕、下其餘）、dedup 正確、warning 獨立；py_compile 全過
- [ ] 3.1 主管點完成 → 先收「確定完成？[是][否]」；按是才定案；否不寫（實機）
- [ ] 3.2 廠商點完成 → 一鍵暫定（無二次確認）（實機）
- [ ] 3.3 主管每看板只剩一張 bubble：上急迫(含按鈕)、下其餘；同工項不重複（實機）
- [ ] 3.4 無獨立摘要 bubble；空看板不出；標頭無屋主名（實機）
- [ ] 3.5 偽造/越權 confirm、冪等仍正確

## 4. 部署

- [ ] 4.1 bump customer-service + notifier image（`scripts/bump-linebot-image.sh`）
- [ ] 4.2 部署後主管/廠商各路徑實機驗證 3.1–3.5