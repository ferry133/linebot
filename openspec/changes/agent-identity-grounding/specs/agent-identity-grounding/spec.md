## ADDED Requirements

### Requirement: 已知身分者不再被索取身分

當 `line_users` 已知使用者的角色與其指派專案（系統提示已注入該使用者的進行中專案）時，客服 agent MUST NOT 反問「你是誰／請報名字／請給案場」。對「我／我的案子／我有哪些工作」這類自指問題，agent SHALL 將「我」對應到已注入的專案，並 SHALL 透過 `query_trello` 查詢這些專案作答。身分注入段落 SHALL 明確宣告身分已確認且禁止再詢問。

#### Scenario: 廠商問自己的案子
- **WHEN** 已指派專案的 vendor 傳「我有哪些案子在做？」
- **THEN** agent 以 `query_trello` 查其已指派專案
- **THEN** agent 回覆其專案清單/進度，且不詢問他是誰或要他報名字

#### Scenario: 自指的待辦查詢
- **WHEN** 已知使用者傳「我這邊還有哪些工作要做？」
- **THEN** agent 以其已注入專案進行查詢作答，不索取身分

#### Scenario: 客戶問自己案子的進度
- **WHEN** 已指派專案的 customer 傳「我的工程到哪了？」
- **THEN** agent 查其專案進度作答，不要求自我介紹

### Requirement: 不獎勵未實際查詢的資料型回答

情節記憶的品質評分 SHALL NOT 僅以回覆字數判定成功。當一則回覆**未呼叫任何工具**且未轉人工（escalate）時，其品質分 SHALL 低於「成功」門檻（即不會在記憶回放中被標為成功範例），以避免「沒查就回／反問身分」的非回答被存成成功 episode 並被 `_recall` 回放而自我增強。使用工具完成的回覆 SHALL 仍可獲得成功分。

#### Scenario: 反問身分的非回答不被評為成功
- **WHEN** 對一個資料型問題，agent 未呼叫工具、只回了一段（即使很長）要求對方表明身分的文字
- **THEN** 該回合的品質分低於成功門檻，不被存為「成功」episode

#### Scenario: 實際查詢的回答仍可得成功分
- **WHEN** agent 呼叫 `query_trello` 並據以回覆
- **THEN** 該回合可獲成功品質分，照常存入記憶

#### Scenario: 不再回放錯誤模式
- **WHEN** 後續 `_recall` 為相似情境檢索過往經驗
- **THEN** 先前「反問身分」的非回答不以「✓ 成功」呈現，不再誘導 agent 重複該行為
