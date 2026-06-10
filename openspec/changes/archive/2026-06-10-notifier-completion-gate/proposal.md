## Why

`check_item()` 的到期／逾期條件（#3～#6）**只判斷日期**，完全沒檢查工項是否已完成，也沒看清單名稱。結果：已標記完成、且已移到「已完成」欄的卡片，只要結束日過了仍持續噴「已逾期 X 天」（實測截圖：`[@(sa),20260505-20260512]` 已完成卻報「已逾期 28 天」）。這與 `trello-line-design.md` 既有規格「#3～#6 共用 card 未完成定義」不符 —— 規格寫了 gate，但程式從未實作。

## What Changes

- **完成嚴格以打勾判定**（只有帶 `[@(...)]` 標記的「檢查項」才算）：
  - card 本身（desc 標記）→ `dueComplete == true`
  - to-do（checklist 標記）→ `state == "complete"`
  - 清單名稱、未標記的 to-do 勾選**不**作為完成依據。
- **抓取 `dueComplete` 欄位**：`get_cards()` 與 `get_board_full()` 的 card fields 補上 `dueComplete`（目前沒抓）。
- **修正 #3～#6**：標記項目**未完成才發送**到期／逾期通知（`active = not is_complete`）。**清單名稱不再當抑制條件**。
- **新增 minor 警告**：整張卡所有檢查項皆完成、但卡片不在「已完成」欄 → morning 早報附加「已完成但未歸欄」提醒（複用 alias 警告機制）。
- **#1／#2（開始日相關）維持不變**。不改 DB schema、不加環境變數。

> 設計原則：完成嚴格認打勾（`dueComplete`/`state`）。實測「保護進場」`dueComplete=true`（單卡 API 確認），加 `dueComplete` 欄位後 `get_cards` 正確讀到 → 該卡被正確抑制。若某卡確實未打勾（`dueComplete≠true`），即使在「已完成」欄或未標記 to-do 全勾，仍視為未完成、照常逾期 —— 促使團隊以打勾表達完成。

## Capabilities

### New Capabilities
- `notification-completion-gate`: 定義到期／逾期通知（#3～#6）必須尊重「完成狀態」與「清單階段」的觸發前提。

### Modified Capabilities
<!-- 無 -->

## Impact

- **程式**：`trello_line_notifier.py`
  - `get_cards()` / `get_board_full()`：card fields 加 `dueComplete`。
  - `check_item()`：新增 `is_complete` 參數；#3～#6 的 `add()` 以 `not is_complete` 為前提（不看清單名稱）。
  - `run_checks()`：呼叫端傳 `is_complete`（card desc → `dueComplete`；checklist → `state`）；並逐卡彙整「所有檢查項完成且不在已完成欄」→ 收集器，於 morning 摘要 render minor 警告。
- **行為**：打勾的標記項目不再收到到期/逾期通知；未打勾的維持原樣（不論清單欄）。完成但未歸欄的卡 → 早報多一條 minor 提醒。
- **風險**：完成嚴格認 `dueComplete`/`state`；未打勾的已歸欄卡仍會逾期（見 What Changes 的已知後果）。
