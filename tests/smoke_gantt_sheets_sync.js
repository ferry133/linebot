// smoke: 工期表 Apps Script（gantt_sheets_sync.gs）的工項定義與 spec work-item-tag 一致。
//
// 以 node 的 vm 真的載入 .gs 原始碼，只把 Apps Script 的全域服務（PropertiesService /
// UrlFetchApp / Utilities / Logger）換成固定資料；Trello 回傳形狀照 2026-10-19 量到的示範卡。
//
// 跑法：node tests/smoke_gantt_sheets_sync.js
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const COMPANY = "66f123294afc4db9701158e2";
const GHOST = "69f46e8af8d92446166bb05b";
const item = (id, name, due = null, idMember = null, state = "incomplete") => ({ id, name, due, idMember, state });

const CARDS = [
  { id: "C108", name: "108.[人造石@(石凱)] 施工", idList: "L1", start: "2026-11-02T00:00:00.000Z",
    due: "2026-11-03T09:00:00.000Z", dueComplete: false, desc: "[@(石凱),20261102-20261104] 施工",
    checklists: [{ checkItems: [
      item("I1", "丈量 (系統櫃立好後）", "2026-10-21T06:00:00.000Z"),
      item("I2", "下坎水槽寄送到廠商預先安裝", "2026-10-23T06:00:00.000Z", COMPANY),
      item("I3", "現場附帶安裝品先準備 (水龍頭, 瓦斯爐, 電磁爐, 檯面垃圾桶,...)"),
    ] }] },
  { id: "C200", name: "200. 雜項", idList: "L1", start: null, due: null, dueComplete: false, desc: "",
    checklists: [{ checkItems: [item("I5", "清潔", "2026-10-28T06:00:00.000Z")] }] },
  { id: "C300", name: "300.[水電@(阿明)] 配管", idList: "L1", start: null, due: null, dueComplete: false, desc: "",
    checklists: [{ checkItems: [item("I6", "配管", "2026-10-29T06:00:00.000Z", GHOST)] }] },
];

// 假 Sheet：記錄 insertColumnsAfter／getRange 寬度；其餘方法一律可串接的 no-op
function fakeSheet(maxCols, lastRow) {
  const log = { inserted: 0, ranges: [] };
  const chain = new Proxy({}, { get: () => () => chain });
  const sheet = new Proxy({
    getMaxColumns: () => maxCols,
    getLastRow: () => lastRow,
    insertColumnsAfter: (_after, n) => { log.inserted += n; },
    getRange: (r, c, nr, nc) => { log.ranges.push([r, c, nr, nc]); return chain; },
  }, { get: (t, k) => (k in t ? t[k] : () => chain) });
  return { sheet, log };
}

function load(memberMeOk, sheet, now) {
  const props = { TRELLO_API_KEY: "k", TRELLO_TOKEN: "t" };
  const fetch = (url) => {
    const p = new URL(url).pathname.replace("/1", "");
    let body, code = 200;
    if (p === "/organizations/jiahomedesign1/boards") body = [{ id: "B1", name: "竹北王宅" }];
    else if (p === "/boards/B1/lists") body = [{ id: "L1", name: "執行中" }];
    else if (p === "/boards/B1/cards") {
      const qs = new URL(url).searchParams;
      // 欄位沒要求就不回（與 Trello 行為一致）→ 驗到 fetch 參數確實補了 start/due
      const fields = (qs.get("fields") || "").split(",");
      body = CARDS.map(c => Object.fromEntries(Object.entries(c).filter(([k]) =>
        ["id", "checklists"].includes(k) || fields.includes(k))));
    } else if (p === "/members/me") { if (memberMeOk) body = { id: COMPANY }; else code = 500; }
    else throw new Error("unexpected fetch " + p);
    return { getResponseCode: () => code, getContentText: () => JSON.stringify(body ?? {}) };
  };
  const ctx = {
    PropertiesService: { getScriptProperties: () => ({ getProperty: k => props[k] || null }) },
    UrlFetchApp: { fetch },
    Utilities: { formatDate: (d, tz, f) => new Intl.DateTimeFormat("en-CA", { timeZone: tz,
      year: "numeric", month: "2-digit", day: "2-digit" }).format(d).replace(/-/g, "") },
    Logger: { log: () => {} },
    SpreadsheetApp: { getActiveSpreadsheet: () => ({ getSheetByName: () => sheet, getActiveSheet: () => sheet, toast: () => {} }) },
  };
  if (now) {   // 固定「今天」
    const RealDate = Date;
    ctx.Date = class extends RealDate { constructor(...a) { super(...(a.length ? a : [now])); } };
  }
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "gantt_sheets_sync.gs"), "utf8"), ctx);
  return ctx;
}

const fails = [];
const check = (name, cond, detail) => {
  console.log((cond ? "PASS " : "FAIL ") + name + (!cond && detail !== undefined ? "  [" + JSON.stringify(detail) + "]" : ""));
  if (!cond) fails.push(name);
};
const ymd = d => d ? `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}` : null;

let ctx = load(true);
let rows = ctx.collectItems_();
const byLabel = Object.fromEntries(rows.filter(r => r.type === "item").map(r => [r.label, r]));
const card = rows.find(r => r.type === "card" && r.card === "108.[人造石@(石凱)] 施工");
check("卡片列：原生寫法合併進卡片摘要列（Trello 日期 11/02–11/03，石凱）",
  card && ymd(card.start) === "20261102" && ymd(card.end) === "20261103" && card.names === "石凱", card);
check("原生卡片不再另出一列工項", !byLabel["108.[人造石] 施工"], Object.keys(byLabel));
check("卡片摘要列進度仍只計待辦項（0/2）", card && card.label === "0/2 完成", card && card.label);
const a = byLabel["丈量 (系統櫃立好後）"];
check("丈量：繼承石凱，只有結束日 10/21", a && a.names === "石凱" && a.start === null && ymd(a.end) === "20261021", a);
const b = byLabel["下坎水槽寄送到廠商預先安裝"];
check("下坎水槽：負責人「公司」，只有結束日 10/23", b && b.names === "公司" && ymd(b.end) === "20261023", b);
check("現場附帶安裝品：沒有日期 → 不出現", !Object.keys(byLabel).some(k => k.startsWith("現場附帶")));
check("無卡片負責人＋未指派 → 不出現", !byLabel["清潔"]);
check("失效成員 → 退回卡片負責人", byLabel["配管"] && byLabel["配管"].names === "阿明", byLabel["配管"]);

ctx = load(false);
rows = ctx.collectItems_();
const labels = rows.filter(r => r.type === "item").map(r => r.label);
check("公司帳號查不到 → 指派的待辦項 fail-closed", !labels.includes("下坎水槽寄送到廠商預先安裝") && !labels.includes("配管"), labels);
check("公司帳號查不到 → 未指派的照常繼承", labels.includes("丈量 (系統櫃立好後）"), labels);

// ── 甘特範圍動態延長（舊版固定 26 週，止於 2026-10-24）──
const NOW = "2026-10-19T12:00:00+08:00";
let fk = fakeSheet(190, 50);
ctx = load(true, fk.sheet, NOW);
ctx.syncTrelloGantt();
const gStart = () => ymd(vm.runInContext("GANTT_START", ctx));
const gEnd = () => { const d = new Date(vm.runInContext("GANTT_START", ctx)); d.setDate(d.getDate() + vm.runInContext("GANTT_DAYS", ctx) - 1); return d; };
// 最早未完成：丈量 10/21（10/19 之後）→ 起點不晚於今天 → 今天所在週日 10/18
check("起點：未完成工項都在今天之後 → 今天那週的週日 10/18", gStart() === "20261018", gStart());
check("終點：今天後 8 週 → 12/19 週六（9 週）", ymd(gEnd()) === "20261219" && vm.runInContext("GANTT_WEEKS", ctx) === 9, [ymd(gEnd()), vm.runInContext("GANTT_WEEKS", ctx)]);
check("欄數足夠時不補欄（190 ≥ 8+63）", fk.log.inserted === 0, fk.log.inserted);
// 逾期未完成 10/01 → 起點回推到 09/28 週日
CARDS[1].checklists[0].checkItems[0].due = "2026-10-01T06:00:00.000Z";
CARDS[1].name = "200. [雜項@(阿明)] 清潔";
ctx = load(true, fakeSheet(190, 50).sheet, NOW);
ctx.syncTrelloGantt();
check("起點：逾期未完成 10/01 → 09/27 週日", gStart() === "20260927", gStart());
// 很久以前的逾期 2026-03-01 → 最多回溯 8 週（08/24）→ 對齊週日 08/23
CARDS[1].checklists[0].checkItems[0].due = "2026-03-01T06:00:00.000Z";
ctx = load(true, fakeSheet(190, 50).sheet, NOW);
ctx.syncTrelloGantt();
check("起點：最多回溯今天前 8 週 → 08/23 週日", gStart() === "20260823", gStart());
// 已完成的舊工項不拉早起點
CARDS[1].checklists[0].checkItems[0].state = "complete";
ctx = load(true, fakeSheet(190, 50).sheet, NOW);
ctx.syncTrelloGantt();
check("起點：已完成的舊工項不影響 → 10/18", gStart() === "20261018", gStart());
CARDS[1].checklists[0].checkItems[0] = item("I5", "清潔", "2026-10-28T06:00:00.000Z");
CARDS[1].name = "200. 雜項";
fk = fakeSheet(10, 50);
ctx = load(true, fk.sheet, NOW);
ctx.syncTrelloGantt();
check("欄數不足時補欄（10 → 8+63）", fk.log.inserted === 8 + 63 - 10, fk.log.inserted);
CARDS[0].due = "2027-01-20T09:00:00.000Z";   // 工項日期比 today+8w 更晚 → 涵蓋它
fk = fakeSheet(400, 50);
ctx = load(true, fk.sheet, NOW);
ctx.syncTrelloGantt();
const lastDay = gEnd();
check("最晚工項 2027-01-20 落在範圍內，終點為週六", ymd(lastDay) >= "20270120" && lastDay.getDay() === 6, ymd(lastDay));
check("上次較長留下的多餘欄被清掉而不是刪掉", fk.log.inserted === 0 && fk.log.ranges.some(([r, c, nr, nc]) => c === 8 + vm.runInContext("GANTT_DAYS", ctx) + 1 && nc === 400 - 8 - vm.runInContext("GANTT_DAYS", ctx)), fk.log.ranges.slice(0, 3));
CARDS[0].due = "2062-01-20T09:00:00.000Z";   // 誤植年份 → 上限 104 週
ctx = load(true, fakeSheet(190, 50).sheet, NOW);
ctx.syncTrelloGantt();
check("誤植年份時上限 104 週", vm.runInContext("GANTT_WEEKS", ctx) === 104, vm.runInContext("GANTT_WEEKS", ctx));

console.log(fails.length ? `\n${fails.length} FAIL: ${JSON.stringify(fails)}` : "\nALL PASS");
process.exit(fails.length ? 1 : 0);
