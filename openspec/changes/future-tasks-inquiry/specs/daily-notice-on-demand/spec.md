## MODIFIED Requirements

### Requirement: Rich Menu 提供未來工項入口
Rich Menu SHALL 提供一格「未來工項」作為未來/過去區間工項清單入口,採 **postback（`data=o=future`，無參數=預設未來1月）**;此入口與「今日提醒」「使用說明」並列於同一 Rich Menu(三格)。單日查詢(datetimepicker `o=someday`)**不再**佔 Rich Menu 一級入口,改由「未來工項」回覆內的「📅 指定日期」quick-reply 提供(見 `future-tasks-inquiry`)。**每日內容本身 MUST NOT 放 datetimepicker 按鈕**(入口統一由 Rich Menu / quick-reply 提供)。

#### Scenario: Rich Menu 有未來工項入口
- **WHEN** 使用者開啟 Rich Menu
- **THEN** 有「未來工項」一格,點按以預設(未來1月)回覆區間工項清單並附方向×視窗 quick-reply

#### Scenario: 單日查詢改由 quick-reply 進入
- **WHEN** 使用者要查特定單一日期
- **THEN** 於「未來工項」回覆點「📅 指定日期」→ 彈出 datetimepicker(`o=someday`),Rich Menu 不再有獨立「查其他日期」格

#### Scenario: 每日內容不含日期選擇器按鈕
- **WHEN** 使用者拉取今日或 someday 內容
- **THEN** 內容中 MUST NOT 出現 datetimepicker 按鈕(入口在 Rich Menu / quick-reply)
