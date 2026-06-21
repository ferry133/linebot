## Why

廠商（role=vendor）原本只做**看板層級**授權：assigned 看板上的工項全都看得到，包含同看板其他負責人的工作。實際發生：larryoffice（vendor）問客服「這裡還有哪些工作要做?」→ 回了整個看板 59 筆（含 57 筆別人的）；而每日通知/拉取也曾因 `larry→larryoffice` 鏡像把主管內容（含待主管確認卡）複製給 larryoffice。需把廠商可見性收斂到**擁有者層級**（只看自己被 `[@(alias)]` 指派的工項），並移除該鏡像。

> 本變更為**回溯記錄已上線行為**（PRs #3、#4，image `2b63d3b`）；程式碼已部署，僅補齊 spec。

## What Changes

- 廠商工項可見性由「看板層級」收斂為「**擁有者層級**」：vendor 只看到 names 含其 alias 的工項。
- 此界線同時套用於**對話查詢**（`query_trello`，customer-service 帶 `owner_alias`、trello-agent 過濾）與**每日通知/Rich Menu 拉取**（`run_checks` 產出按 uid/被指派過濾）。
- customer（屋主）維持**整看板**可見（看自己案場全貌）；admin/employee 不變（全部）。
- 移除 `larry→larryoffice` 鏡像：它會把 larry（主管）全部內部項目與待主管確認卡複製給 larryoffice（vendor），造成越權外洩。

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `role-based-access-control`: vendor 存取範圍由看板層級細化為擁有者層級；新增「廠商工項可見性以擁有者為界（跨對話與通知兩條路徑）」要求，並明訂不得有跨帳號鏡像外洩。

## Impact

- 已實作於 `agents/customer_service.py`（`_query_trello` 帶 `owner_alias`；vendor 系統提示）、`agents/trello_agent.py`（owner 過濾）、`trello_line_notifier.py`（移除鏡像）。無 DB / API 變更。
- 純 spec 補齊；無新程式碼。
