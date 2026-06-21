## 1. 對話查詢 owner 過濾（已實作於 #4）

- [x] 1.1 `customer_service._query_trello` 依 role 計算 `owner_alias`（vendor=alias，其餘 None），帶入 MQTT request
- [x] 1.2 vendor 系統提示加註：query_trello 僅回自己負責工項，勿列他人
- [x] 1.3 `trello_agent._query` 於板層授權後再以 `owner_alias` 過濾（None=off，""=匹配空）

## 2. 移除跨帳號鏡像（已實作於 #3）

- [x] 2.1 移除 `run_checks` 的 `larry→larryoffice` 鏡像

## 3. 驗證（已完成）

- [x] 3.1 larryoffice 對話查詢：board-only 59 → owner-scoped 2，隱藏 57 筆他人工項
- [x] 3.2 larryoffice 拉取：1 bubble、0 確認卡（僅自身工項）；larry 仍得摘要+確認卡
