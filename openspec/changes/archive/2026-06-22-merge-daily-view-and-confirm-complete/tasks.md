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
- [x] 3.1 confirm-flex + gate 已部署（`o=complete_confirm`/`o=complete_cancel` 按鈕驗證）；主管實點 round-trip 待屋主端眼驗
- [x] 3.2 廠商分支未變（一鍵暫定）；已部署
- [x] 3.3 主管每看板一張 bubble：3 看板=3 張「今日工程」、含上段按鈕+下段「其餘進行中工項」（live 驗）
- [x] 3.4 無獨立摘要樹 bubble（僅 warnings 獨立）；空看板不出；標頭無屋主名（live blob 比對 0 leak）
- [x] 3.5 commit 步驟重用既有 owner/supervisor+allowed_board_ids+冪等驗證（未變更）

## 4. 部署

- [x] 4.1 bump 至 `2f13a92`（customer-service + notifier + admin）
- [x] 4.2 部署後 live 驗證：合併 bubble、無屋主名、confirm-flex 正確