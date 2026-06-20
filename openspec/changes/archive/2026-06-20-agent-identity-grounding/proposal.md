## Why

客服 agent 對**已知身分**的使用者仍反問「你是誰？」。larryoffice（vendor，已指派 3 個專案）問「我有哪些案子在做？」時，agent 不查 Trello、反而要他報名字。

production 追到兩個疊加的根因：

1. **身分注入太軟**：`_reason_and_act` 雖注入「## 此使用者的進行中專案」，但措辭只說「請以這些專案名稱辨識」。`_recall` 同時注入的「成功範例」幾乎都是**帶名字的查詢**（「曾宇晟進度」「劉正群案進度」），Claude 學到「查詢要有名字」，於是對沒帶名字的「我的案子」反問身分。

2. **情節記憶自我增強**：`_evaluate` **只看回覆字數**——`len > 100 → 0.8`。一段流暢的「你是誰？」非回答字數很長 → 評 0.8「成功」→ 存成 episode → `_recall` 把它當「✓ 成功範例」再注入 → 每問一次身分就強化一次，越滾越糟。

（已先做資料清理：刪除 5 筆污染 episodes、清 working_memory，larryoffice 當下已正常；但不根治會復發。）

## What Changes

- **強化身分注入**：把專案區塊改為明確宣告「系統已確認此使用者身分，**禁止反問他是誰／要他報名字**；當他說『我／我的案子／我的工作』即指下列專案，直接用 `query_trello` 查這些專案作答」。
- **修正品質評分**：`_evaluate` 不再單以字數給高分。**沒有呼叫任何工具的資料型回答**（純文字、未 escalate）最高只給未達「成功」門檻的分數，避免把「沒查就回／反問身分」當成功範例存進記憶並回放。

## Capabilities

### New Capabilities
- `agent-identity-grounding`: 客服 agent 對已知身分使用者的接待原則——以系統已知的角色/專案為準、不重複索取身分；且情節記憶的品質評分不獎勵「未實際查詢的資料型回答」，避免錯誤模式自我增強。

### Modified Capabilities
<!-- 無 spec 層級的既有能力變更；沿用 role-based-access-control 的權限查詢。 -->

## Impact

- **程式碼**：`agents/customer_service.py`
  - `_reason_and_act`：強化「此使用者的進行中專案」注入文字。
  - `_evaluate`：納入 `tools_used`，未呼叫工具的資料型回答不給「成功」分。
- **資料**：無 schema 變更。已完成的污染清理（episodes/working_memory）為一次性、不在本變更範圍。
- **非目標**：不改 `_recall`/記憶檢索機制本身、不改 RBAC 權限邊界、不動 query_trello 工具。
