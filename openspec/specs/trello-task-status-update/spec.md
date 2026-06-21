## Purpose
定義授權使用者如何透過 LINE 提醒卡片按鈕更新 Trello 工項的完成狀態：以 postback 精準定位工項、限工項 owner 或 supervisor 寫入、寫入後失效掃描快取並留稽核留言；廠商的變更先暫定生效並待主管事後追認或退回。
## Requirements
### Requirement: 透過提醒卡片按鈕更新工項完成狀態

提醒（#1–#8）的 Flex 卡片每則工項 SHALL 附「標記完成 / 取消完成」postback 按鈕，`data` 夾帶該工項的 `board_id`、`card_id`、`checkItem_id`（checklist 來源才有）、`source`（card/checklist）與目標 `op`（complete/incomplete）。使用者點按後，系統 SHALL 依該 id 精準定位並執行 Trello 寫入：checklist 工項改 `checkItem.state`、card 層級工項（card desc tag）改 `card.dueComplete`；MUST NOT 移動卡片欄位、MUST NOT 變更日期或標記文字。

#### Scenario: 按鈕標記 checklist 工項完成
- **WHEN** owner 點按某 checklist 工項的「標記完成」按鈕
- **THEN** 系統設定該 `checkItem.state = complete`
- **THEN** agent 回覆已將該工項標記完成

#### Scenario: 按鈕標記 card 層級工項完成
- **WHEN** owner 點按某 card 層級工項（card desc tag）的「標記完成」按鈕
- **THEN** 系統設定該 `card.dueComplete = true`，且不移動卡片欄位
- **THEN** agent 回覆已將該工項標記完成

#### Scenario: 反向取消完成
- **WHEN** owner 點按某已完成工項的「取消完成」按鈕
- **THEN** 系統將 checklist `state` 設為 incomplete 或 card `dueComplete` 設為 false
- **THEN** agent 回覆已取消完成

#### Scenario: 冪等
- **WHEN** 目標工項已處於請求的狀態（如已完成又按「標記完成」）
- **THEN** 系統不重複寫入，回覆該工項已是該狀態

### Requirement: 寫入限工項 owner 或 supervisor

更新工項完成狀態 SHALL 僅允許**該工項的 owner**（操作者的 `line_users.alias_name` 出現在該工項 `[@(who)…]` 的 names 內），或 `role ∈ {admin, employee}` 的 supervisor。customer-service agent MUST 在送出寫入前驗證 owner/supervisor；系統 MUST 依 postback 帶的 card/checkItem id 重新讀取該卡、解析 tag owner 再驗一次，並套用該使用者 `allowed_board_ids` 過濾，確保偽造的 postback 無法越權。

#### Scenario: 非 owner 被拒
- **WHEN** 操作者既非該工項 tag 的 owner、也非 admin/employee
- **THEN** 系統不執行任何 Trello 寫入
- **THEN** agent 婉拒並說明僅該工項負責人可操作

#### Scenario: owner 放行
- **WHEN** 操作者的 alias 出現在該工項 `[@(who)…]` 內
- **THEN** 系統執行其請求的完成/取消寫入

#### Scenario: supervisor 放行
- **WHEN** 操作者 role 為 admin 或 employee（非該工項 owner）
- **THEN** 系統仍執行其請求的寫入

#### Scenario: 偽造 postback 越權被擋
- **WHEN** 收到的 postback 指向操作者 `allowed_board_ids` 之外、或非其負責的工項
- **THEN** 系統不執行寫入並回報無權限

### Requirement: 寫入後狀態一致

寫入成功後系統 SHALL 失效 trello-agent 的工項掃描快取（publish invalidate），使後續查詢反映最新狀態。寫入失敗（Trello API 回非 2xx）時 agent MUST 回報失敗，MUST NOT 謊報成功。

#### Scenario: 寫入後查詢反映新狀態
- **WHEN** 一工項剛被標記完成
- **THEN** 後續對該工項的查詢顯示為完成狀態（不受 60 秒快取殘留影響）

#### Scenario: 寫入失敗如實回報
- **WHEN** Trello API 對寫入回傳非 2xx
- **THEN** agent 回報更新失敗，不宣稱已完成

### Requirement: 操作稽核留言

每次完成狀態寫入成功後，系統 SHALL 於該卡片的「留言與活動」新增一則稽核留言，內容 MUST 包含**操作者**（LINE 顯示名與 alias）、**操作時間**（台北時區）、**動作**（標記完成／取消完成）與**工項**（label）。稽核留言失敗 MUST NOT 影響已成功的狀態寫入結果，但 SHALL 記錄 log。

#### Scenario: 寫入後新增稽核留言
- **WHEN** 一工項經由按鈕被標記完成且 Trello 寫入成功
- **THEN** 系統於該卡片新增一則留言，記載操作者、台北時間、「標記完成」與該工項 label

#### Scenario: 取消完成亦留稽核
- **WHEN** 一工項被取消完成且寫入成功
- **THEN** 留言記載操作者、時間與「取消完成」與該工項 label

#### Scenario: 留言失敗不影響狀態結果
- **WHEN** 狀態寫入成功但新增留言失敗
- **THEN** agent 仍回報狀態更新成功，並記錄留言失敗的 log

### Requirement: 廠商變更為暫定並待主管追認

當操作者為工項 owner 但**非** admin/employee（即廠商）時，其完成/取消變更 SHALL **立即在 Trello 生效（暫定）**，同時系統 SHALL 於 `task_confirmations` 建立一筆 `status=pending` 紀錄（記錄目標工項、claim 的目標狀態、操作者、時間，以及 claim 當下的**卡片名稱**快照）。系統 **MUST NOT** 於標記當下逐一即時推播主管；該 pending 改由 supervisor 的每日內容（經 on-demand 拉取，見 `daily-notice-on-demand` 與 `notification-daily-summary`）以可操作確認卡呈現。廠商標記後系統 SHALL 回覆廠商「已暫定，將通知主管確認」。

#### Scenario: 廠商標記完成為暫定
- **WHEN** 廠商（owner 非 supervisor）點按某工項「標記完成」
- **THEN** 系統立即將該工項在 Trello 設為完成
- **THEN** 系統建立一筆 pending 追認紀錄（含卡片名稱快照），並回覆廠商已暫定待主管確認

#### Scenario: 標記當下不即時推播主管
- **WHEN** 廠商建立一筆 pending 暫定變更
- **THEN** 系統 MUST NOT 於該當下推播任何主管確認卡片
- **THEN** 該 pending 於 supervisor 下次拉取每日內容時才呈現

#### Scenario: supervisor 直接標記免追認
- **WHEN** 操作者 role 為 admin 或 employee 並直接標記某工項完成/取消
- **THEN** 變更立即定案，系統 MUST NOT 建立 pending 追認紀錄、MUST NOT 要求再追認

### Requirement: 主管事後追認或退回

supervisor SHALL 能對 pending 的廠商暫定變更事後**確認**或**退回**。確認 SHALL 將該紀錄標為 `confirmed`（Trello 維持暫定後的狀態，定案）；退回 SHALL 將該紀錄標為 `rejected` 並把 Trello **還原為變更前狀態**。確認/退回 MUST 僅允許 admin/employee；對已處理（confirmed/rejected）的紀錄再次操作 SHALL 視為冪等並回覆已處理。兩種結果皆 SHALL 於卡片留言記錄追認者與時間。

#### Scenario: 確認定案
- **WHEN** supervisor 對某 pending 變更點按「確認」
- **THEN** 該追認紀錄標為 confirmed，Trello 狀態不變
- **THEN** 卡片新增留言記錄追認者與時間

#### Scenario: 退回還原
- **WHEN** supervisor 對某 pending 變更點按「退回」
- **THEN** 系統將該工項在 Trello 還原為變更前狀態（complete↔incomplete 反向）
- **THEN** 該追認紀錄標為 rejected，卡片新增留言記錄退回者與時間

#### Scenario: 非 supervisor 不可追認
- **WHEN** 非 admin/employee 嘗試確認或退回
- **THEN** 系統不改變任何紀錄或 Trello 狀態，並婉拒

#### Scenario: 重複處理冪等
- **WHEN** 對已 confirmed 或 rejected 的紀錄再次確認/退回
- **THEN** 系統不重複動作，回覆該項已處理

