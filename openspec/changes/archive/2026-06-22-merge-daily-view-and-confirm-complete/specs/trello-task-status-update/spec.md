## ADDED Requirements

### Requirement: 主管完成定案前二次確認
為避免在小螢幕誤觸造成不可逆的定案，當操作者為 supervisor（`role ∈ {admin, employee}`）點按某工項「完成」時，系統 **MUST NOT** 於第一下即寫入；SHALL 先回覆一則確認提示（含工項 label 與「是 / 否」兩個 postback 按鈕，「是」夾帶與原請求相同的 `board_id`/`card_id`/`checkItem_id`/`source`）。僅當 supervisor 再點「是」時，系統才執行定案寫入；點「否」或不回應則不寫入。**廠商（owner 非 supervisor）維持一鍵標記**（暫定生效並待主管追認，已具退回安全網），不套用二次確認。定案步驟 SHALL 照常套用 owner/supervisor 與 `allowed_board_ids` 越權驗證及冪等規則。

#### Scenario: 主管點完成 → 先確認
- **WHEN** role∈{admin,employee} 點某工項「完成」
- **THEN** 系統不寫入 Trello，先回覆「確定將『{label}』標記完成？」含「是/否」
- **THEN** 僅當再點「是」才設定 complete（定案）；點「否」不變更

#### Scenario: 廠商維持一鍵
- **WHEN** owner 非 supervisor 的廠商點「完成」
- **THEN** 系統一鍵暫定生效並建立 pending（不要求二次確認）

#### Scenario: 確認步驟仍驗權與冪等
- **WHEN** 主管點「是」定案
- **THEN** 系統重讀卡片驗 owner/supervisor 與 allowed_board_ids；已是完成狀態則冪等回覆不重複寫入
