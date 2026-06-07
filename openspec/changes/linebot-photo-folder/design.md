## Context

`synology-photo-tagger` 正在做「auto-move」功能（依 GPS-感知的 tag 自動把相片移到 `/photo/officephoto/<X>/YYYYMM/`）。`<X>` 需要：
- 短（長案描述不適合做檔案系統的長期 folder 名）
- 跨「型態」共用（同一個物理案場的「設計」「結構基礎」「室內裝修」相片該丟同一個 photo folder，不該被型態切碎）
- 線索可由 linebot 提供（linebot 是 project 的 source of truth）

目前 `linebot.projects.name` 是一個合併好的字串（`{業主}-{案場}-{型態}`），但：
- 沒有結構化欄位
- `室內裝修` vs `室內裝修工程` 等 enum 變體已存在於既有 row
- 純字串切分（split-last-dash）不可靠

本 change 把這三個元件拆成獨立 column，讓 admin UI 與 API 都能精準操作；同時對外暴露 derived `photo_folder`（= `{業主}-{案場}`），給 synology-photo-tagger 用。

## Goals / Non-Goals

**Goals:**
- 結構化儲存 owner / site / type，未來不再用 string parsing
- 自動 compose `name`，避免 admin 手動拼錯
- 提供穩定 derived `photo_folder` 給 synology-photo-tagger 串接
- 向下相容（既有 row 不需 migrate）

**Non-Goals:**
- 不在本 change 強制 backfill 既有 row（要 admin 一筆筆編輯補）
- 不調整 `case_number` / `nas_path` 邏輯（multi-到-1 已由 `allow-shared-nas-folder` 處理過）
- 不擴大 `project_type` enum（先支援目前三種；新類型再開 change）
- 不在 linebot 端執行 synology FileStation 操作（synology-photo-tagger 那邊做）

## Decisions

### D1: 三個分開的 column，不用 jsonb / composite type
- **選擇**：`owner_name TEXT`、`site_name TEXT`、`project_type TEXT`
- **理由**：query 簡單、index 直接；jsonb 對 3 個欄位過度設計；composite type postgres 支援度差
- **trade-off**：未來 enum 擴增要 `ALTER CHECK CONSTRAINT`，可接受

### D2: `project_type` 用 CHECK constraint enum
- **選擇**：`CHECK (project_type IS NULL OR project_type IN ('設計', '結構基礎', '室內裝修', '軟裝'))`
- **理由**：純資料層 enforcement 比 application-level 更可靠
- **替代**：postgres `CREATE TYPE` enum — 但 migrate 時改 enum 比改 CHECK 麻煩
- **trade-off**：要加新類型時就改 migration（可接受）

### D3: `name` 在三欄位齊全時自動 compose；不齊全時保留 admin 自填
- **選擇**：app-layer 在 INSERT/UPDATE 時組裝 `name`
- **替代**：generated column（postgres v12+）— 但既有 row 的舊 `name` 會被覆蓋成 null，破壞向下相容
- **trade-off**：邏輯散在 app code，要避免有 DB 直寫繞過

### D4: `photo_folder` 是 derived，不存 DB
- **選擇**：app code 在 GET response 即時組裝 `f"{owner_name}-{site_name}"`
- **理由**：完全 derived，沒有 sync 問題
- **替代**：generated column — 但每次 API call 開銷比 derived 大不到哪去，且 generated column 對既有 row 行為要驗證

### D5: 既有 row 不 auto-backfill
- **選擇**：3 個新欄位皆 nullable、不寫 backfill script
- **理由**：既有 `name` 字串格式多樣（`室內裝修工程` 變體），自動解析會出錯
- **作法**：admin UI 在編輯既有 row 時顯示「請補充」橫幅，使用者主動補
- **trade-off**：過渡期既有 row `photo_folder = null`，synology-photo-tagger 對這些案要 fallback 到「不 auto-move」

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| 既有 row backfill 不完，synology-photo-tagger 拿不到 `photo_folder` → auto-move 對舊案無效 | Acceptable：舊案仍可用「手動備份」按鈕走既有 UI 流程；同時 admin UI 提示請補欄位 |
| 同一 `owner-site` 不同 `type` 同時建立 → `name` 雖然各自合法但前端可能誤判為重複 | `name` 在 DB 沒 UNIQUE 約束；UI 顯示時靠 `case_number` 為主 key |
| 業主名 / 案場名 含 `-` 會破壞「split-last-dash」邏輯 | 本 change 後不再做 split-last-dash；外部 consumer（synology-photo-tagger）直接用 `photo_folder` derived 欄位 |
| 老 admin 不知道有新欄位 → 一直建沒結構化欄位的 row | UI 預設把三欄位放最顯眼位置、`legacy mode` 才允許單 `name` 輸入 |

## Migration Plan

- Migration `008_project_photo_folder.sql`：3 個 ALTER TABLE ADD COLUMN + 1 CHECK constraint
- 既有 row 三欄位皆 null（DB default）
- 部署後 admin UI 即可開始用三欄位輸入；舊 row 編輯時提示補欄位
- 沒有 backfill data step；沒有破壞性回滾風險（純加欄位）
- 回滾：drop 3 column + drop constraint（資料無損失，因為新欄位是新加的）
