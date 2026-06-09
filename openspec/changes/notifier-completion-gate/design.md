## Context

`check_item()` 的到期/逾期分支（#3 noon、#4 morning、#5/#6 evening）原本只判斷日期。`get_cards()`／`get_board_full()` 原本未抓 `dueComplete`。

實測線上資料：`dueComplete` 幾乎全為 `None`（團隊未使用 Trello「標示完成」鈕）；清單名稱高度不一致、含 emoji 前綴（`🔄 未執行`、`✅ 已完成`…）。使用者拍板：**完成嚴格以打勾判定**，清單名稱只用來產生「未歸欄」提醒、不當抑制。

## Goals / Non-Goals

**Goals:**
- 打勾完成（card `dueComplete` / checklist `state`）的標記項目不再收到 #3～#6。
- 完成但未歸「已完成」欄的卡片 → morning 早報 minor 提醒。
- #1／#2 與 noon #7/#8、#9 摘要不變。

**Non-Goals:**
- 不以「未標記 to-do 是否勾選」或「清單名稱」推導完成。
- 不改 DB/env、不動訊息格式與其他條件。

## Decisions

### D1. 抓 `dueComplete`
`get_cards()`／`get_board_full()` 的 card fields 加 `dueComplete`。

### D2. 完成判定（嚴格打勾）
- card description 標記：`is_complete = (card.get("dueComplete") is True)`（None/False 皆視為未完成）。
- checklist 項目標記：`is_complete = (item.get("state") == "complete")`。
由呼叫端計算後傳入 `check_item(..., is_complete=...)`。

### D3. 抑制只看完成，不看清單名稱
`check_item()` 內 `active = not is_complete`；#3／#4／#5／#6 的 `add()` 以 `active` 為前提。#1／#2 不加。**移除**先前的 `"已完成" not in list_name` 抑制條件。

### D4. 「完成但未歸欄」minor 警告（morning）
新增 module-level 收集器 `_complete_unfiled: list[str]`，`run_checks()` 起始清空。逐卡彙整其「檢查項」（帶標記者）：
- card 有 desc 標記 → 該檢查項完成 = `dueComplete is True`
- 每個帶標記 checklist 項目 → 完成 = `state == complete`

當「卡片至少有一個檢查項 且 全部檢查項完成 且 `"已完成" not in list_name`」→ append `f"{board_name}/{card_name}"`。morning 摘要 render 時，若收集器非空，附加「✅ 已完成但未歸『已完成』欄」段落（與 alias 警告相同的附加方式）。noon/evening 不 render。

## Risks / Trade-offs

- **dueComplete 取得**：實測 `get_cards`（`/1/boards/{id}/cards`）在 `fields` 明確加 `dueComplete` 後可正確回傳 `true`（保護進場已驗證）。舊碼未請求此欄位故回 None —— 部署修正版後即正確。
- **未打勾即逾期**：若卡確實 `dueComplete≠true`（即使已歸欄）仍判未完成、持續 #6。此為刻意設計（完成=打勾）。
- **per-card 彙整位置**：在 `run_checks()` 既有 per-card 迴圈內累積 `card_has_check`／`card_all_complete` 旗標即可，無需額外 Trello 呼叫。
- **collector 為 module 狀態**：one-shot CronJob 每次新行程；仍於 run 起始 `clear()` 確保可測。
