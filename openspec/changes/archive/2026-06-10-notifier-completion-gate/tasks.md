## 1. 抓取 dueComplete 欄位

- [x] 1.1 `get_cards()` 的 `fields` 加 `dueComplete`
- [x] 1.2 `get_board_full()` 的 `card_fields` 加 `dueComplete`

## 2. 完成判定 + 抑制（只看打勾，不看清單名稱）

- [x] 2.1 `check_item()` 簽名加 `is_complete: bool = False`
- [x] 2.2 `check_item()` 內 `active = not is_complete`（**移除**「已完成 not in list_name」條件）
- [x] 2.3 #4／#3／#5／#6 的 `add()` 以 `active` 為前提；#1／#2 不加
- [x] 3.1 card description 呼叫傳 `is_complete=bool(card.get("dueComplete"))`
- [x] 3.2 checklist 項目呼叫傳 `is_complete=(item.get("state") == "complete")`

## 3. 「完成但未歸欄」minor 警告

- [x] 3.3 新增 module-level `_complete_unfiled: list[str]`，`run_checks()` 起始 `clear()`
- [x] 3.4 逐卡彙整檢查項完成狀態（desc 標記看 `dueComplete`、checklist 標記看 `state`）；當「有檢查項 且 全完成 且 `'已完成' not in list_name`」→ append `board/card`
- [x] 3.5 morning 摘要 render：收集器非空時附加「✅ 已完成但未歸『已完成』欄」段落；noon/evening 不 render

## 4. 驗證（對線上資料、唯讀不發送）

- [x] 4.1 「保護進場」（desc 標記、`dueComplete=true`、在已完成欄）→ 確認**不再**逾期通知（被完成抑制），且**不**進「未歸欄」警告（已歸欄）
- [x] 4.2 合成：desc 標記 `dueComplete=true`、清單非已完成 → 不發逾期、且進「未歸欄」警告
- [x] 4.3 合成：checklist 標記 `state=complete`、清單非已完成、且為該卡唯一檢查項 → 不發逾期、進警告
- [x] 4.4 合成：未完成標記（任一載體）→ 照常逾期、不進警告；確認清單名稱（emoji 前綴）不影響抑制
