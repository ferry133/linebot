## Context

現況：`trello_line_notifier.py` 以 `mode ∈ {morning,noon,evening}` 三批次執行（三個 CronJob），各 mode 評估不同觸發條件；morning 另含 #9 摘要，內含純文字「待主管確認」清單。廠商按提醒卡片標記後，`CustomerServiceAgent._handle_status_update` 寫 Trello → 建 pending → `_notify_supervisors` 對每位主管即時各推一張 `_confirm_flex`（[agents/customer_service.py:710-735](../../../agents/customer_service.py#L710-L735)）。

近期已導入 Reply API：gateway 將 `reply_token` 經 MQTT 串到 agent，outbox **reply 優先、push fallback**（capability `line-message-delivery`）。**reply 免費、不計額度；push 計入 200/月。**

痛點：即時逐人推 × 三批次 → 額度爆量；確認卡缺專案/卡片定位。

## Goals / Non-Goals

**Goals:**
- 三批次合併為單一每日批次（評估 #1–#9），語意不變。
- 主動 push **只送 vendor**；主管與客戶改 on-demand 拉取（reply＝免費）。
- 取消廠商標記的即時推播；pending 改在主管拉取內容中以**可操作、含定位**確認卡呈現。

**Non-Goals:**
- 不改觸發條件判定本身（僅合併時機與過濾收件人）。
- 不改 `line-message-delivery` spec（on-demand reply 已符合其既有「reply 優先、push fallback」規則）。
- 確認卡與摘要不做獨立收件人旋鈕（共用 role）。

## Decisions

**1. 合併批次：單一每日執行評估 #1–#9**
保留各條件函式，移除依 mode 分流的時機限制，單次評估全部。#5「今日 HH:MM 已逾期」清晨幾乎不成立 → 由 #4 涵蓋、視為惰性；**#6 取消 `is_weekday` 守衛**（逾期於所有執行日含週日皆呈現；批次排程 Sun–Fri，週六不跑）。

**2. 內容引擎共用、交付管道分流**
`run_checks` 產出 `(uid, board, rec)` 後：
- **主動 push（CronJob）**：過濾 `role(uid) = vendor` 才送；其餘角色不 push。空內容（該 vendor 無 bubble）→ 不呼叫 `send_flex`（skip-empty）。
- **on-demand 拉取（agent，`o=daily`）**：針對單一請求者 uid 組裝其角色內容（supervisor 另加摘要＋確認卡），以 reply token 回覆（免費），無 token 才 push fallback。一律回覆，無內容回「今日無提醒」。
- 為重用，將「某 uid 的今日 bubble 清單」組裝抽成共用函式，notifier 與 agent 皆呼叫。

**3. 取消即時推播，pending 走拉取**
`_handle_status_update` 廠商分支移除 `_notify_supervisors`；仍寫 Trello（暫定）＋建 pending＋回覆廠商。確認卡建構移到共用內容組裝（supervisor 拉取時產生）。`_handle_confirmation`（按按鈕後處理）不變，postback 仍 `o=confirm|reject&cid=`。

**4. `card_name` 落庫**
`task_confirmations` 加 `card_name TEXT`（migration 012），`_insert_pending` 在 claim 當下寫入（該時點有 live card）。渲染確認卡：卡片名讀 `card_name`；專案名由 `board_id` 查 `projects.name`（新 helper，查無→後備值）。避免拉取時逐筆 `get_card`。

**5. Rich Menu**
建立單一預設 Rich Menu，含「📋 今日提醒」postback `o=daily`。內容於回覆時依角色決定，毋須多個選單。Rich Menu 透過 LINE API 一次性註冊並設為 default。

## Risks / Trade-offs

- [拉取慢 → reply token 過期 → fallback push（計費）] → 倚賴 trello-agent 既有掃描快取；快取熱時拉取在 token 窗口內完成維持免費。冷快取偶發掉 push 可接受。
- [主管只靠拉取 → 不點就漏看 pending] → 為使用者選擇之取捨；pending 不會消失，下次拉取仍在。
- [push 僅 vendor → 內部到期/停滯(#7)/摘要(#9) 無 push 對象] → 這些本就是內部資訊，改由主管拉取呈現；符合預期。
- [12 bubble 截斷] → 確認卡優先保留，溢出隔次拉取再現。
- [部署遺漏致跑舊碼] → 三→一 CronJob、notifier 與 agent image 須在 jg-base 同步 bump（多檔釘 sha，見 CLAUDE.md），否則殘留 noon/evening CronJob 照舊 push。
- [`_internal_recipients()` 去重後 3 個 line_id vs 4 個 admin/employee 帳號] → 主管現在改拉取，受影響較小，但仍應查核此資料問題。
