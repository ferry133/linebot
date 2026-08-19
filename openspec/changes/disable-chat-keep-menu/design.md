## Context

customer-service agent（`agents/customer_service.py`）目前 `_on_message` 的文字分支順序為：
`GUIDE_KEYWORDS` → `DAILY_KEYWORDS` → 未來/過去關鍵字 → **其餘全部進 `_process()` → `_run()` 五步循環（Claude）**。
postback 分支（`_process_postback`）在更前面就 return，本來就不經 Claude。

因此「關閉對話」精確地等同於：**攔截掉最後那個 fallback 分支**，其餘路徑一律不動。這是本次改動能保持極小面積的原因。

## Goals / Non-Goals

**Goals:**
- 一個環境變數即可關閉／恢復對話，且**恢復不需改程式碼**。
- 關閉期間 Anthropic API 呼叫數為 0；不產生任何記憶寫入（避免停用期間污染 `episodes`／`knowledge`）。
- 今日提醒、未來工項、使用說明（Rich Menu + 關鍵字 + 相關 postback）與工項完成／主管追認完全不受影響。
- 關閉期間仍**一定會回覆**（Reply API，免費），使用者不會遇到已讀不回。
- 停用期間的來訊**不沉沒**：原文轉發主管通知群，由人接手回覆。

**Non-Goals:**
- 不刪除 Claude loop、TOOLS、`_recall`／`_reflect` 等程式碼（要能原地恢復）。
- 不做轉發的去重／限流／工單化（同一人連續發問會產生多則轉發）。
- 不動 Claude 的 `escalate_to_manager` 工具本身（它隨對話一起停用；轉發是另一條路徑）。
- 不改 trello-agent、每日 CronJob、Rich Menu 版面（gateway 僅新增 `group_id` 透傳）。

## Decisions

**D1：開關放在 customer-service agent，而非 gateway。**
gateway 只負責驗簽／轉送／出口，攔在 gateway 會連 postback 與關鍵字一起難以區分（gateway 不查角色也不做內容組裝）。攔在 `_on_message` 的最後 fallback 是唯一只影響「自由對話」的位置。
_替代方案_：在 gateway 過濾文字訊息 → 需要在兩處維護保留關鍵字清單，必然分岔，否決。

**D2：`CHAT_ENABLED` 預設 `false`（關閉）。**
本次目的就是關閉；預設關閉表示只要 merge + bump image 即生效，不必同時改 `jg-base`（跨 repo）。恢復時在 `jg-base` deploy 設 `CHAT_ENABLED=true`，或之後再提一個 change 把預設翻回。
_替代方案_：預設 `true` + 在 jg-base 設 `false` → 關閉這件事同時要動兩個 repo，且「關閉狀態」只存在於叢集、repo 上讀不出來，否決。

**D3：解析採寬鬆真值。** `os.environ.get("CHAT_ENABLED", "false").strip().lower() in ("1","true","yes","on")`；其餘值（含空字串、拼錯）一律視為關閉——**fail-closed**，避免打錯字造成非預期的 LLM 花費。

**D4：關閉時的回覆是一則固定文字，經既有 OUTBOX（帶 `reply_token`）送出。**
沿用 `_reply()`，因此自動取得「Reply 優先、失敗才 Push」的既有出口語意，不新增傳送路徑。

**D5：關閉時完全跳過 `_perceive/_recall/_reason_and_act/_reflect`。**
不寫 `working_memory`，避免停用期間累積無工具、低品質 episode；也讓恢復後的記憶延續停用前的狀態。

**D6a：停用期間的來訊轉發主管群，且來源是通知群時不轉。**
`_forward_offline_message` 走與 escalate 相同的出口（抽出 `_notify_managers` + `_manager_targets`：優先 `LINE_NOTIFY_GROUP_ID`，未設定則查 `line_users` 的 admin，無 admin 才退 employee），訊息含時間／顯示名（alias）／角色／一對一或群組／原文（截 800 字）。bot 本身是通知群成員，故該群的訊息也會進 webhook——若不判斷來源，等於把該群訊息推回同一群製造回音；因此 gateway 在 inbox payload 帶上 `group_id`（`source.groupId` 或 `roomId`），agent 據此跳過。
_替代方案_：以「角色為 admin/employee 就不轉」代替來源判斷 → 通知群裡的未登錄成員（visitor）仍會造成回音，且會漏掉主管在一對一的提問，否決。

**D6c：主管對象改由 `line_users.role` 決定，不用 contacts 的固定名字。**
原 `_escalate` 的回退是 `load_contacts().get("sa"/"larry")`，但該 map 的 key 是 LINE 顯示名（實測為 `詹阿瀨 larry`、`廖ㄚ莎✨samantha✨` 等 21 筆），與 alias 不同 → **永遠取不到**。production 的 `LINE_NOTIFY_GROUP_ID` 又是空字串，因此 escalate 通知一直被靜默丟棄，而 log 仍寫著「已通知」。改以 `line_users` 的 role 查（admin 優先、無 admin 才 employee），並讓 `_notify_managers` 回傳實際送達數、0 送達時留 warning——**不可鑑別的通知不能讀起來像成功的通知**。

**D6b：轉發在背景 thread 執行。**
`send_line` 是 HTTP 呼叫，而 `_on_message` 跑在 MQTT callback thread；先 `_reply()`（僅 MQTT publish，快）再開 thread 轉發，維持與既有 handler 相同的「不阻塞 loop」慣例。

**D6：開關在模組載入時求值一次（module-level 常數）。**
與現有 `KNOWLEDGE_DIR`、`MODEL` 等一致；切換以 pod 重啟（改 env 本來就會 rollout）生效，行為可預期。

## Risks / Trade-offs

- **[主管群噪音]** 停用期間每則來訊都會轉發，多人同時提問會刷群 → 訊息前綴統一為 `📨 客服對話停用期間來訊（需人工回覆）` 便於辨識/搜尋；若量大再加去重或限流。
- **[轉發失敗是靜默的]** `send_line` 失敗不會讓使用者感知（他已收到「已轉交專人」）→ 轉發成功與跳過各自留 log（`Forwarded offline msg` / `Offline msg from notify group`），可從 pod log 量測，而非只能事後推論。
- **[誤以為系統壞了]** 使用者可能把固定訊息當成故障 → 文字中明說「客服對話功能暫停中」，並列出三個可用功能名稱，與 Rich Menu 三格用字一致。
- **[恢復時忘了 env]** 之後想恢復卻只 bump image 會仍是關閉 → 在 proposal/tasks 與 `CLAUDE.md` 註明恢復步驟為「jg-base 設 `CHAT_ENABLED=true` + rollout」。
- **[fail-closed 的代價]** env 打錯字時是「靜默維持關閉」，讀起來與正確關閉一樣 → 啟動時 log 一行目前模式（`chat=enabled/disabled`），使狀態可從 pod log 量測，而不是只能從行為推論。

## Migration Plan

1. merge → CI build image。
2. `jg-base`：`scripts/bump-linebot-image.sh <sha>` → commit/push → `flux reconcile`（無需改 deploy.yaml env）。
3. 驗證：`kubectl logs deploy/linebot-customer-service` 應出現 `chat=disabled`；LINE 傳一般文字 → 收到引導訊息、主管群收到轉發、log 出現 `Forwarded offline msg`；點三格選單 → 內容正常。
4. 回復對話：`jg-base` deploy.yaml 加 `CHAT_ENABLED: "true"` → rollout；log 應出現 `chat=enabled`。
