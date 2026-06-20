## 1. 強化身分注入（agents/customer_service.py）

- [x] 1.1 `_reason_and_act`：把「## 此使用者的進行中專案」區塊改為明確指令——宣告身分已確認、禁止反問他是誰/要他報名字；「我／我的案子／我的工作」對應到已注入專案；直接 `query_trello` 查這些專案作答。維持置於系統提示最後（memory_context 之後）。

## 2. 修正品質評分（agents/customer_service.py）

- [x] 2.1 `_evaluate` 納入 `result.tools_used`：未 error、未 escalated、且未使用工具的回答最高給低於 0.7 的分（不論字數）；有工具者維持依字數 0.6/0.8。
- [x] 2.2 確認 `_reflect`：無工具回答因此不再以 `quality≥0.7` 存為「成功」episode；知識面（需 `tools_used`）不受影響。

## 3. 本機驗證

- [x] 3.1 `ast.parse` 通過；`_evaluate` 單元：有工具長回覆→0.8、無工具長回覆→<0.7、escalated→0.5、error→0.1。
- [x] 3.2 以真實/stub 重建 larryoffice 情境（強化注入 + 含 memory_context）跑 Claude：對「我有哪些案子在做？」回覆為 `query_trello`、不問身分（A/B 對照舊注入）。

## 4. 部署

- [x] 4.1 commit + push linebot；CI green。
- [x] 4.2 bump jg-base 8 個 image pins（deploy ×4 / admin ×1 / cronjobs ×3，**不含** migrate-contacts-job）→ Flux reconcile（kustomization `linebot` + `trello-notifier`）。

## 5. 部署後驗證

- [ ] 5.1 真機：larryoffice 連問數次「我有哪些案子在做？」「我還有哪些工作？」皆直接查詢作答、不再反問身分；確認未再生成「反問身分」的高分 episode。
- [ ] 5.2 抽驗一個 customer 帳號的自指查詢同樣正常。
