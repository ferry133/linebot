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

// end-only items（只有結束日，無開始日）使用淡色版本
const BAR_COLORS_LIGHT = {
  complete:   "#b7e1c4",
  incomplete: "#c5d9fb",
  overdue:    "#f5c6c2",
  desc:       "#fde9a2",
};

// 奇偶週交替底色（無 bar 時顯示）
const BAND       = ["#ffffff", "#d9d9d9"];
const BAND_TODAY = "#f9cb9c";  // 今天欄的底色（橙色）


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
  if (start) {
    // start-only：只繪製開始日後 7 天（含）的窗口
    const effEnd = new Date(start);
    effEnd.setDate(effEnd.getDate() + 6);
    return day >= start && day <= effEnd;
  }
  if (end) {
    // end-only：只繪製結束日前 7 天（含）的窗口
    const effStart = new Date(end);
    effStart.setDate(effStart.getDate() - 6);
    return day >= effStart && day <= end;
  }
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

// 一次抓取「已註冊負責人」alias 清單（line_users.alias_name，與 LINE 通知同一來源），
// 回傳小寫 Set 存記憶體供整次同步重用；未設定時回 null（不過濾，graceful）。
// Script Properties 需設：ALIASES_URL（如 https://<gateway 網域>/aliases）、
// GANTT_API_TOKEN（專屬 token，與 gateway 的 GANTT_API_TOKEN 相同；以 Bearer 標頭送出）。
function fetchValidAliases_() {
  const props = PropertiesService.getScriptProperties();
  const url   = props.getProperty("ALIASES_URL");
  const token = props.getProperty("GANTT_API_TOKEN");
  if (!url || !token) return null;
  const res = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    headers: { "Authorization": "Bearer " + token },
  });
  if (res.getResponseCode() !== 200) {
    Logger.log(`aliases API ${res.getResponseCode()} — 略過負責人過濾`);
    return null;  // 取不到 → 不過濾（甘特圖照常產生），避免整次同步失敗
  }
  const data = JSON.parse(res.getContentText());
  return new Set((data.aliases || []).map(a => String(a).toLowerCase()));
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

// 反向掃描 rows，標記各組的 last 旗標，供 ASCII 樹狀符號使用。
// card rows: lastInBoard（該 board 最後一張卡）、lastInList（該 board+list 最後一張卡）
// item rows: lastItem（該 card 最後一個工項）
function markLastFlags_(rows) {
  const seenBoards    = new Set();
  const seenLists     = new Set();
  const seenCardItems = new Set();

  for (let i = rows.length - 1; i >= 0; i--) {
    const r = rows[i];
    if (r.type === 'card') {
      const boardKey = r.board;
      const listKey  = `${r.board}||${r.list}`;
      r.lastInBoard = !seenBoards.has(boardKey);
      r.lastInList  = !seenLists.has(listKey);
      seenBoards.add(boardKey);
      seenLists.add(listKey);
    } else {
      const cardKey = `${r.board}||${r.list}||${r.card}`;
      r.lastItem = !seenCardItems.has(cardKey);
      seenCardItems.add(cardKey);
    }
  }
}

function collectItems_() {
  const boards = trelloGet_(`/organizations/${WORKSPACE_ID}/boards`, "filter=open");
  const rows   = [];
  const today  = new Date(); today.setHours(0, 0, 0, 0);

  // 一次抓取有效 alias，整次同步重用。負責人有任一不在清單(=LINE「查無對應」)→ 略過該工項。
  const validAliases = fetchValidAliases_();
  const hasUnmatchedOwner = (names) =>
    validAliases !== null && names.some(n => !validAliases.has(String(n).toLowerCase()));

  for (const board of boards) {
    if (board.name.includes("母版")) continue;

    const lists   = trelloGet_(`/boards/${board.id}/lists`, "fields=name");
    const listMap = Object.fromEntries(lists.map(l => [l.id, l.name]));
    const cards   = trelloGet_(`/boards/${board.id}/cards`, "checklists=all&fields=name,desc,idList,dueComplete");

    for (const card of cards) {

      const listName = listMap[card.idList] || "";

      // Card description tag — 不計入進度統計，但以 item row 形式顯示。
      // 其完成 = 卡片 dueComplete（與通知一致），否則 dueComplete 的完成卡會被誤判逾期。
      let descRow = null;
      if (card.desc) {
        const parsed = parseTag_(card.desc.split("\n")[0]);
        if (parsed && !hasUnmatchedOwner(parsed.names)) {
          descRow = {
            type:  'item',
            board: board.name,
            list:  listName,
            card:  card.name,
            label: parsed.label,
            names: parsed.names.join("、"),
            start: parsed.start,
            end:   parsed.end,
            state: card.dueComplete ? 'complete' : 'incomplete',
          };
        }
      }

      // Checklist 項目（有 [@...] 標記的）
      const itemRows = [];
      for (const cl of (card.checklists || [])) {
        for (const item of (cl.checkItems || [])) {
          const parsed = parseTag_(item.name);
          if (!parsed) continue;
          if (hasUnmatchedOwner(parsed.names)) continue;  // 負責人未在用戶管理(查無對應)→ 不列入
          itemRows.push({
            type:  'item',
            board: board.name,
            list:  listName,
            card:  card.name,
            label: parsed.label,
            names: parsed.names.join("、"),
            start: parsed.start,
            end:   parsed.end,
            state: item.state,
          });
        }
      }

      // Card-level 統計（只計算 checklist items）
      const totalCount    = itemRows.length;
      const completeCount = itemRows.filter(r => r.state === 'complete').length;

      let cardStart = null;
      let cardEnd   = null;
      for (const r of itemRows) {
        if (r.start) cardStart = cardStart ? (r.start < cardStart ? r.start : cardStart) : r.start;
        if (r.end)   cardEnd   = cardEnd   ? (r.end   > cardEnd   ? r.end   : cardEnd)   : r.end;
      }

      // 無任何標記（no checklist tags, no desc tag）→ 直接跳過
      if (totalCount === 0 && descRow === null) continue;

      // desc-only：desc tag 的日期/名稱直接合併進 card summary row，不單獨輸出
      const isDescOnly  = totalCount === 0 && descRow !== null;
      const cardNames   = isDescOnly ? descRow.names : '';
      const finalStart  = isDescOnly ? descRow.start : cardStart;
      const finalEnd    = isDescOnly ? descRow.end   : cardEnd;

      const hasOverdue  = isDescOnly
        ? (descRow.end && descRow.end < today && !card.dueComplete)
        : itemRows.some(r => r.end && r.end < today && r.state !== 'complete');
      const allComplete  = card.dueComplete === true || (totalCount > 0 && completeCount === totalCount);
      const isNotStarted = !allComplete && finalStart && finalStart < today && listName.includes("未執行");
      const cardBarColor = allComplete ? BAR_COLORS.complete
                         : hasOverdue  ? BAR_COLORS.overdue
                                       : BAR_COLORS.incomplete;

      // Card summary row
      rows.push({
        type:        'card',
        board:       board.name,
        list:        listName,
        card:        card.name,
        label:       `${completeCount}/${totalCount} 完成`,
        names:       cardNames,
        start:       finalStart,
        end:         finalEnd,
        state:       '',
        barColor:    cardBarColor,
        status:      allComplete  ? "✓ 完成"
                   : isNotStarted ? "未開始"
                   : hasOverdue   ? "逾期"
                                  : "未完成",
        startOverdue: isNotStarted,
      });

      if (descRow && !isDescOnly) rows.push(descRow);  // 有 checklist items 時才單獨顯示 desc row
      if (itemRows.length)        rows.push(...itemRows);
    }
  }

  markLastFlags_(rows);
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

  // 預計算每天的奇偶週底色（今天欄用橙色，標題列與資料列共用）
  const bandRow = days.map((d, i) =>
    d.getTime() === today.getTime() ? BAND_TODAY : BAND[Math.floor(i / 7) % 2]
  );

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

  // 清除舊資料與舊顏色（第 3 列起），並取消舊版留下的隱藏列
  const lastRow = sheet.getLastRow();
  if (lastRow >= 3) {
    const clearRange = sheet.getRange(3, 1, lastRow - 2, 8 + GANTT_DAYS);
    clearRange.clearContent();
    clearRange.setBackground("#ffffff");
    clearRange.setFontColor("#000000");
    sheet.showRows(3, lastRow - 2);
  }

  // 取得最新 Trello 資料（card summary rows + item rows）
  const items = collectItems_();
  if (items.length === 0) {
    sheet.getRange(3, 1).setValue("（無符合標記的工項）");
    return;
  }

  // 組成資料矩陣與甘特色票矩陣
  const dataRows   = [];
  const ganttBgAll = [];
  const cellBgCols = [];  // A~H 欄底色（card row=灰，item row=白）
  let   prevBoard  = null;
  let   prevList   = null;

  for (const r of items) {
    if (r.type === 'card') {
      // A/B 欄：board/list 有變動才填名稱，否則填 ASCII 樹狀連接符
      const showBoard = r.board !== prevBoard;
      const showList  = showBoard || r.list !== prevList;

      const aVal = showBoard ? r.board : (r.lastInBoard ? "└─ " : "│");
      const bVal = showList  ? r.list  : (r.lastInList  ? "└─ " : "├─ ");

      prevBoard = r.board;
      prevList  = r.list;

      const ganttRow = days.map((d, i) =>
        (r.start || r.end) && dayOverlaps_(d, r.start, r.end) ? r.barColor : bandRow[i]
      );
      ganttBgAll.push(ganttRow);
      cellBgCols.push("#e8e8e8");

      const ganttVals = Array(GANTT_DAYS).fill("");
      if (r.start) { const i = Math.round((r.start - GANTT_START) / 86400000); if (i >= 0 && i < GANTT_DAYS) ganttVals[i] = "S"; }
      if (r.end)   { const i = Math.round((r.end   - GANTT_START) / 86400000); if (i >= 0 && i < GANTT_DAYS) ganttVals[i] = "E"; }

      dataRows.push([
        aVal, bVal, r.card, r.label, r.names,
        r.start ? fmt(r.start, "yyyy/MM/dd") : "",
        r.end   ? fmt(r.end,   "yyyy/MM/dd") : "",
        r.status,
        ...ganttVals,
      ]);

    } else { // item
      const isOverdue   = r.end && r.end < today && r.state !== 'complete';
      const isStartOnly = !!r.start && !r.end;
      const isEndOnly   = !r.start && !!r.end;
      const isFaded     = isStartOnly || isEndOnly;
      const barKey      = r.state === 'complete'   ? 'complete'
                        : isOverdue                ? 'overdue'
                        : r.state === 'incomplete' ? 'incomplete'
                        : 'desc';
      const barColor    = isFaded ? BAR_COLORS_LIGHT[barKey] : BAR_COLORS[barKey];

      const ganttRow = days.map((d, i) =>
        dayOverlaps_(d, r.start, r.end) ? barColor : bandRow[i]
      );
      ganttBgAll.push(ganttRow);
      cellBgCols.push("#ffffff");

      const cVal  = r.lastItem ? "└─ " : "├─ ";
      const status = r.state === 'complete'   ? "✓ 完成"
                   : isOverdue                ? "逾期"
                   : r.state === 'incomplete' ? "未完成"
                   : "";

      const ganttVals = Array(GANTT_DAYS).fill("");
      if (r.start) { const i = Math.round((r.start - GANTT_START) / 86400000); if (i >= 0 && i < GANTT_DAYS) ganttVals[i] = "S"; }
      if (r.end)   { const i = Math.round((r.end   - GANTT_START) / 86400000); if (i >= 0 && i < GANTT_DAYS) ganttVals[i] = "E"; }

      dataRows.push([
        "", "", cVal, r.label, r.names,
        r.start ? fmt(r.start, "yyyy/MM/dd") : "",
        r.end   ? fmt(r.end,   "yyyy/MM/dd") : "",
        status,
        ...ganttVals,
      ]);
    }
  }

  // 寫入文字資料
  sheet.getRange(3, 1, dataRows.length, dataRows[0].length).setValues(dataRows);

  // A~H 欄底色（card summary rows = 灰色 #e8e8e8，item rows = 白色）
  sheet.getRange(3, 1, cellBgCols.length, 8)
    .setBackgrounds(cellBgCols.map(c => Array(8).fill(c)));

  // 套用甘特背景色（第 9 欄起）
  sheet.getRange(3, 9, ganttBgAll.length, GANTT_DAYS).setBackgrounds(ganttBgAll);

  // 逾期工項：結束日欄（G）顯示紅色字體
  const endColColors = items.map(r => {
    if (r.type !== 'item') return ["#000000"];
    const isOverdue = r.end && r.end < today && r.state !== 'complete';
    return [isOverdue ? "#ea4335" : "#000000"];
  });
  sheet.getRange(3, 7, items.length, 1).setFontColors(endColColors);

  // 未開始 card（未執行清單 + 開始日已過）：F欄開始日、H欄狀態 顯示紅色字體
  const startColColors  = items.map(r => [r.startOverdue ? "#ea4335" : "#000000"]);
  const statusColColors = items.map(r => {
    if (r.type === 'card') return [r.startOverdue || r.status === "逾期" ? "#ea4335" : "#000000"];
    const isOverdue = r.end && r.end < today && r.state !== 'complete';
    return [isOverdue ? "#ea4335" : "#000000"];
  });
  sheet.getRange(3, 6, items.length, 1).setFontColors(startColColors);
  sheet.getRange(3, 8, items.length, 1).setFontColors(statusColColors);

  // 時間戳記
  sheet.getRange(3 + dataRows.length + 1, 1)
    .setValue(`上次同步：${fmt(new Date(), "yyyy/MM/dd HH:mm")}`);

  const itemCount = items.filter(r => r.type === 'item').length;
  SpreadsheetApp.getActiveSpreadsheet()
    .toast(`✅ 已同步 ${itemCount} 個工項`, "Trello 同步完成", 5);
}
