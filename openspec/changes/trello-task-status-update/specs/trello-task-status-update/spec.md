## ADDED Requirements

### Requirement: 透過提醒卡片按鈕更新工項完成狀態

#1–#8 提醒的 Flex 卡片每則工項 SHALL 附「標記完成 / 取消完成」postback 按鈕，`data` 夾帶該工項的 `board_id`、`card_id`、`checkItem_id`（checklist 來源才有）、`source`（card/checklist）與目標 `op`（complete/incomplete）。使用者點按後，系統 SHALL 依該 id 精準定位並執行 Trello 寫入：checklist 工項改 `checkItem.state`、card 層級工項（card desc tag）改 `card.dueComplete`；MUST NOT 移動卡片欄位、MUST NOT 變更日期或標記文字。

#### Scenario: 按鈕標記 checklist 工項完成
- **WHEN** owner 點按某 checklist 工項的「標記完成」按鈕
- **THEN** trello-agent 設定該 `checkItem.state = complete`
- **THEN** agent 回覆已將該工項標記完成

#### Scenario: 按鈕標記 card 層級工項完成
- **WHEN** owner 點按某 card 層級工項（card desc tag）的「標記完成」按鈕
- **THEN** trello-agent 設定該 `card.dueComplete = true`，且不移動卡片欄位
- **THEN** agent 回覆已將該工項標記完成

#### Scenario: 反向取消完成
- **WHEN** owner 點按某已完成工項的「取消完成」按鈕
- **THEN** trello-agent 將 checklist `state` 設為 incomplete 或 card `dueComplete` 設為 false
- **THEN** agent 回覆已取消完成

#### Scenario: 冪等
- **WHEN** 目標工項已處於請求的狀態（如已完成又按「標記完成」）
- **THEN** trello-agent 不重複寫入，回覆該工項已是該狀態

### Requirement: 寫入限工項 owner 或 supervisor

更新工項完成狀態 SHALL 僅允許**該工項的 owner**（操作者的 `line_users.alias_name` 出現在該工項 `[@(who)…]` 的 names 內），或 `role ∈ {admin, employee}` 的 supervisor。customer-service agent MUST 在送出寫入前驗證 owner/supervisor；trello-agent MUST 依 postback 帶的 card/checkItem id 重新讀取該卡、解析 tag owner 再驗一次，並套用該使用者 `allowed_board_ids` 過濾，確保偽造的 postback 無法越權。

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
- **THEN** trello-agent 不執行寫入並回報無權限

### Requirement: 寫入後狀態一致

trello-agent 寫入成功後 SHALL 失效其工項掃描快取，使後續查詢反映最新狀態。寫入失敗（Trello API 回非 2xx）時 agent MUST 回報失敗，MUST NOT 謊報成功。

#### Scenario: 寫入後查詢反映新狀態
- **WHEN** 一工項剛被標記完成
- **THEN** 後續對該工項的查詢顯示為完成狀態（不受 60 秒快取殘留影響）

#### Scenario: 寫入失敗如實回報
- **WHEN** Trello API 對寫入回傳非 2xx
- **THEN** agent 回報更新失敗，不宣稱已完成
