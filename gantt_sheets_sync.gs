/**
 * Trello → Google Sheets 甘特圖同步腳本
 *
 * 安裝步驟：
 *   1. 開啟 Google Sheets → 擴充功能 → Apps Script
 *   2. 貼上此檔案內容，儲存
 *   3. 設定 Script Properties（專案設定 → 指令碼屬性）：
 *        TRELLO_API_KEY   你的 Trello API Key
 *        TRELLO_TOKEN     你的 Trello Token
 *   4. 執行一次 syncTrelloGantt() 以授權
 *   5. （選用）設定時間觸發：觸發條件 → 新增觸發條件 → syncTrelloGantt → 每天
 *
 * 工作表名稱預設為 "gantt"（可修改下方 SHEET_NAME）
 * 甘特欄：每欄一天，26 週共 182 欄，奇偶週交替底色，bar 以狀態色標示
 */

const WORKSPACE_ID = "jiahomedesign1";
const SHEET_NAME   = "gantt";
const GANTT_START  = new Date(2026, 3, 26); // 2026-04-26（週日，月份從 0 起算）
const GANTT_WEEKS  = 26;
const GANTT_DAYS   = GANTT_WEEKS * 7;      // 182 天

const DOW_ZH = ["日","一","二","三","四","五","六"];

// 甘特 bar 顏色（覆蓋在底色上）
const BAR_COLORS = {
  complete:   "#34a853",  // 綠 — 已完成
  incomplete: "#4285f4",  // 藍 — 進行中
  overdue:    "#ea4335",  // 紅 — 已逾期
  desc:       "#fbbc04",  // 黃 — card description 項目
};

// 奇偶週交替底色（無 bar 時顯示）
const BAND = ["#ffffff", "#d9d9d9"];


// ─── 工具函式 ──────────────────────────────────────────────

function getDays_() {
  const days = [];
  for (let i = 0; i < GANTT_DAYS; i++) {
    const d = new Date(GANTT_START);
    d.setDate(d.getDate() + i);
    days.push(d);
  }
  return days;
}

function dayOverlaps_(day, start, end) {
  if (start && end)  return day >= start && day <= end;
  if (start)         return day >= start;
  if (end)           return day <= end;
  return false;
}

function parseDate_(str) {
  if (!str) return null;
  return new Date(
    parseInt(str.slice(0, 4)),
    parseInt(str.slice(4, 6)) - 1,
    parseInt(str.slice(6, 8))
  );
}

function parseTag_(text) {
  const m = text.trim().match(/^\[@((?:@?\([^)]+\))+),(\d{8})?-?(\d{8})?(?::(\d{4}))?\](.*)/);
  if (!m) return null;
  const names = [];
  let nm;
  const nameRe = /\(([^)]+)\)/g;
  while ((nm = nameRe.exec(m[1])) !== null) names.push(nm[1]);
  return { names, start: parseDate_(m[2]), end: parseDate_(m[3]), label: m[5].trim() };
}

function trelloGet_(path, qs) {
  const props = PropertiesService.getScriptProperties();
  const key   = props.getProperty("TRELLO_API_KEY");
  const token = props.getProperty("TRELLO_TOKEN");
  if (!key || !token) throw new Error("請先在 Script Properties 設定 TRELLO_API_KEY 與 TRELLO_TOKEN");
  const url = `https://api.trello.com/1${path}?key=${encodeURIComponent(key)}&token=${encodeURIComponent(token)}${qs ? "&" + qs : ""}`;
  const res = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) throw new Error(`Trello API 錯誤 ${res.getResponseCode()}: ${res.getContentText()}`);
  return JSON.parse(res.getContentText());
}


// ─── 資料收集 ──────────────────────────────────────────────

function collectItems_() {
  const boards = trelloGet_(`/organizations/${WORKSPACE_ID}/boards`, "filter=open");
  const rows   = [];

  for (const board of boards) {
    if (board.name.includes("母版")) continue;

    const lists   = trelloGet_(`/boards/${board.id}/lists`, "fields=name");
    const listMap = Object.fromEntries(lists.map(l => [l.id, l.name]));
    const cards   = trelloGet_(`/boards/${board.id}/cards`, "checklists=all&fields=name,desc,idList,dueComplete");

    for (const card of cards) {
      const listName = listMap[card.idList] || "";

      // Card description 第一行
      if (card.desc) {
        const parsed = parseTag_(card.desc.split("\n")[0]);
        if (parsed) {
          rows.push({ board: board.name, list: listName, card: card.name,
            label: parsed.label,
            names: parsed.names.join("、"),
            // card 層級工項完成 = 卡片 dueComplete（與通知一致），否則完成卡會被誤判逾期
            start: parsed.start, end: parsed.end,
            state: card.dueComplete ? "complete" : "incomplete" });
        }
      }

      // Checklist 項目
      for (const cl of (card.checklists || [])) {
        for (const item of (cl.checkItems || [])) {
          const parsed = parseTag_(item.name);
          if (!parsed) continue;
          rows.push({ board: board.name, list: listName, card: card.name,
            label: parsed.label, names: parsed.names.join("、"),
            start: parsed.start, end: parsed.end, state: item.state });
        }
      }
    }
  }

  return rows;
}


// ─── 主同步函式（從 UI 執行此函式）────────────────────────

function syncTrelloGantt() {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME) || ss.getActiveSheet();
  const days  = getDays_();
  const TZ    = "Asia/Taipei";
  const fmt   = (d, f) => Utilities.formatDate(d, TZ, f);
  const today = new Date(); today.setHours(0, 0, 0, 0);

  // 凍結標題列與左側資訊欄
  sheet.setFrozenRows(2);
  sheet.setFrozenColumns(8);

  // 甘特欄寬：每欄 22px，視覺緊湊
  sheet.setColumnWidths(9, GANTT_DAYS, 22);

  // 預計算每天的奇偶週底色（標題列與資料列共用）
  const bandRow = days.map((d, i) => BAND[Math.floor(i / 7) % 2]);

  // 標題列 1：每週日顯示 "mm/dd~mm/dd"（週日~週六），其餘留空
  const row1 = Array(8).fill("").concat(
    days.map(d => {
      if (d.getDay() !== 0) return "";
      const sat = new Date(d); sat.setDate(sat.getDate() + 6);
      return `${fmt(d, "MM/dd")}~${fmt(sat, "MM/dd")}`;
    })
  );

  // 標題列 2：欄位名 + 每天星期簡稱（日一二三四五六）
  const row2 = ["案件","清單","卡片","工項名稱","負責人","開始日","結束日","狀態"].concat(
    days.map(d => DOW_ZH[d.getDay()])
  );

  // 解除既有合併 → 寫入值 → 每週 7 欄合併為一格
  sheet.getRange(1, 9, 1, GANTT_DAYS).breakApart();
  sheet.getRange(1, 1, 1, row1.length).setValues([row1]);
  sheet.getRange(2, 1, 1, row2.length).setValues([row2]);
  for (let w = 0; w < GANTT_WEEKS; w++) {
    sheet.getRange(1, 9 + w * 7, 1, 7).merge();
  }

  // 標題列甘特區塊套用奇偶週底色
  sheet.getRange(1, 9, 1, GANTT_DAYS).setBackgrounds([bandRow]);
  sheet.getRange(2, 9, 1, GANTT_DAYS).setBackgrounds([bandRow]);

  // 清除舊資料與舊顏色（第 3 列起）
  const lastRow = sheet.getLastRow();
  if (lastRow >= 3) {
    const clearRange = sheet.getRange(3, 1, lastRow - 2, 8 + GANTT_DAYS);
    clearRange.clearContent();
    clearRange.setBackground("#ffffff");
    clearRange.setFontColor("#000000");
  }

  // 取得最新 Trello 資料
  const items = collectItems_();
  if (items.length === 0) {
    sheet.getRange(3, 1).setValue("（無符合標記的工項）");
    return;
  }

  // 組成資料矩陣與甘特色票矩陣
  const dataRows   = [];
  const ganttBgAll = [];

  for (const r of items) {
    const status = r.state === "complete"   ? "✓ 完成"
                 : r.state === "incomplete" ? "進行中"
                 : "";

    const isOverdue = r.end && r.end < today && r.state !== "complete";
    const barColor  = r.state === "complete"   ? BAR_COLORS.complete
                    : isOverdue                ? BAR_COLORS.overdue
                    : r.state === "incomplete" ? BAR_COLORS.incomplete
                    : BAR_COLORS.desc;

    // bar 色覆蓋底色，空格顯示奇偶週底色
    ganttBgAll.push(
      days.map((d, i) => dayOverlaps_(d, r.start, r.end) ? barColor : bandRow[i])
    );

    dataRows.push([
      r.board, r.list, r.card, r.label, r.names,
      r.start ? fmt(r.start, "yyyy/MM/dd") : "",
      r.end   ? fmt(r.end,   "yyyy/MM/dd") : "",
      status,
      ...Array(GANTT_DAYS).fill(""),
    ]);
  }

  // 寫入文字資料
  sheet.getRange(3, 1, dataRows.length, dataRows[0].length).setValues(dataRows);

  // 套用甘特背景色（第 9 欄起）
  sheet.getRange(3, 9, ganttBgAll.length, GANTT_DAYS).setBackgrounds(ganttBgAll);

  // 逾期行：結束日欄（G）顯示紅色
  const endColColors = items.map(r => {
    const isOverdue = r.end && r.end < today && r.state !== "complete";
    return [isOverdue ? "#ea4335" : "#000000"];
  });
  sheet.getRange(3, 7, items.length, 1).setFontColors(endColColors);

  // 時間戳記
  sheet.getRange(3 + dataRows.length + 1, 1)
    .setValue(`上次同步：${fmt(new Date(), "yyyy/MM/dd HH:mm")}`);

  SpreadsheetApp.getActiveSpreadsheet()
    .toast(`✅ 已同步 ${items.length} 個工項`, "Trello 同步完成", 5);
}
