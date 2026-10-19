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

function load(memberMeOk) {
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
  };
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
const card = byLabel["108.[人造石] 施工"];
check("卡片列：原生寫法（Trello 日期 11/02–11/03，石凱）",
  card && ymd(card.start) === "20261102" && ymd(card.end) === "20261103" && card.names === "石凱", card);
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

console.log(fails.length ? `\n${fails.length} FAIL: ${JSON.stringify(fails)}` : "\nALL PASS");
process.exit(fails.length ? 1 : 0);
