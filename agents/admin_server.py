#!/usr/bin/env python3
"""
Admin Web UI — 聯絡人 & 工地權限管理

GET  /                      HTML 管理介面
GET  /api/contacts          列出所有聯絡人
POST /api/contacts          新增
PUT  /api/contacts/<name>   更新
DELETE /api/contacts/<name> 刪除
GET  /api/boards            Trello 看板清單（from DB）
"""

import json
import os
import functools
import logging

from flask import Flask, request, jsonify, Response
from shared.log import setup as _setup_log
from shared.db import db_exec

_setup_log()
log = logging.getLogger(__name__)

app = Flask(__name__)

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge")
CONTACTS_FILE = os.path.join(KNOWLEDGE_DIR, "contacts.json")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "changeme")


# ── Basic Auth ────────────────────────────────────────────────────────────────

def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
            return Response("Unauthorized", 401,
                            {"WWW-Authenticate": 'Basic realm="Linebot Admin"'})
        return f(*args, **kwargs)
    return decorated


# ── Contacts helpers ───────────────────────────────────────────────────────────

def read_contacts() -> dict:
    try:
        with open(CONTACTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {}


def write_contacts(data: dict):
    with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/api/contacts")
@require_auth
def list_contacts():
    return jsonify(read_contacts())


@app.post("/api/contacts")
@require_auth
def add_contact():
    body = request.get_json()
    name = (body.get("name") or "").strip()
    line_id = (body.get("line_id") or "").strip()
    projects = body.get("projects", "*")
    if not name or not line_id:
        return jsonify({"error": "name and line_id are required"}), 400
    contacts = read_contacts()
    if name in contacts:
        return jsonify({"error": f"{name} already exists"}), 409
    contacts[name] = {"line_id": line_id, "projects": projects}
    write_contacts(contacts)
    log.info(f"[admin] Added contact: {name}")
    return jsonify({"ok": True})


@app.put("/api/contacts/<name>")
@require_auth
def update_contact(name: str):
    body = request.get_json()
    contacts = read_contacts()
    if name not in contacts:
        return jsonify({"error": "not found"}), 404
    entry = contacts[name]
    if "line_id" in body:
        entry["line_id"] = body["line_id"].strip()
    if "projects" in body:
        entry["projects"] = body["projects"]
    new_name = (body.get("name") or name).strip()
    if new_name != name:
        contacts[new_name] = contacts.pop(name)
    else:
        contacts[name] = entry
    write_contacts(contacts)
    log.info(f"[admin] Updated contact: {name}")
    return jsonify({"ok": True})


@app.delete("/api/contacts/<name>")
@require_auth
def delete_contact(name: str):
    contacts = read_contacts()
    if name not in contacts:
        return jsonify({"error": "not found"}), 404
    del contacts[name]
    write_contacts(contacts)
    log.info(f"[admin] Deleted contact: {name}")
    return jsonify({"ok": True})


@app.get("/api/boards")
@require_auth
def list_boards():
    rows = db_exec(
        "SELECT board_name FROM trello_boards ORDER BY board_name",
        fetchall=True
    ) or []
    return jsonify([r["board_name"] for r in rows])


# ── HTML UI ───────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LINE 客服管理</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,sans-serif;background:#f5f5f5;color:#333}
header{background:#06c755;color:#fff;padding:16px 24px;display:flex;align-items:center;gap:12px}
header h1{font-size:18px;font-weight:600}
main{max-width:960px;margin:24px auto;padding:0 16px}
.card{background:#fff;border-radius:8px;box-shadow:0 1px 4px #0001;padding:20px;margin-bottom:20px}
h2{font-size:13px;font-weight:600;margin-bottom:16px;color:#888;text-transform:uppercase;letter-spacing:.5px}
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:12px;color:#999;padding:8px 12px;border-bottom:2px solid #eee}
td{padding:10px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}
tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:2px 9px;border-radius:12px;font-size:12px;margin:2px}
.ba{background:#e8f5e9;color:#2e7d32}
.bp{background:#e3f2fd;color:#1565c0}
.btn{padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:500}
.btn-g{background:#06c755;color:#fff}
.btn-r{background:#fff;color:#e53935;border:1px solid #e53935}
.btn-b{background:#fff;color:#1976d2;border:1px solid #1976d2}
.btn+.btn{margin-left:6px}
dialog{border:none;border-radius:12px;padding:24px;width:500px;max-width:95vw;box-shadow:0 8px 32px #0003}
dialog::backdrop{background:#0005}
dialog h3{margin-bottom:18px;font-size:16px}
.field{margin-bottom:14px}
label.lbl{display:block;font-size:13px;color:#666;margin-bottom:5px}
input[type=text]{width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:14px}
input[type=text]:focus{outline:none;border-color:#06c755}
.radio-row{display:flex;gap:20px;margin-bottom:14px}
.radio-row label{font-size:13px;display:flex;align-items:center;gap:6px;cursor:pointer}
.boards-wrap{border:1px solid #ddd;border-radius:6px;padding:10px;max-height:200px;overflow-y:auto;display:flex;flex-wrap:wrap;gap:6px}
.chip{padding:5px 12px;border-radius:16px;background:#f0f0f0;font-size:13px;cursor:pointer;user-select:none;border:1px solid transparent}
.chip.on{background:#e3f2fd;color:#1565c0;border-color:#90caf9}
.df{display:flex;justify-content:flex-end;gap:8px;margin-top:20px}
.empty{text-align:center;padding:32px;color:#bbb;font-size:14px}
#addBtn{margin-bottom:14px}
</style>
</head>
<body>
<header>
  <svg width="26" height="26" viewBox="0 0 24 24" fill="white"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>
  <h1>LINE 客服管理</h1>
</header>
<main>
  <div class="card">
    <h2>聯絡人 / 工地權限</h2>
    <button class="btn btn-g" id="addBtn" onclick="openAdd()">＋ 新增聯絡人</button>
    <table>
      <thead><tr><th>姓名</th><th>LINE User ID</th><th>工地權限</th><th>操作</th></tr></thead>
      <tbody id="tb"><tr><td colspan="4" class="empty">載入中…</td></tr></tbody>
    </table>
  </div>
</main>

<dialog id="dlg">
  <h3 id="dlgT">新增聯絡人</h3>
  <div class="field"><label class="lbl">姓名</label><input type="text" id="fN" placeholder="王小明"></div>
  <div class="field"><label class="lbl">LINE User ID（以 U 開頭）</label><input type="text" id="fL" placeholder="Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"></div>
  <div class="radio-row">
    <label><input type="radio" name="pt" value="all" checked onchange="toggleB(false)"> 員工（全部工地）</label>
    <label><input type="radio" name="pt" value="sel" onchange="toggleB(true)"> 客戶（指定工地）</label>
  </div>
  <div class="field" id="bField" style="display:none">
    <label class="lbl">可存取的工地（點選切換）</label>
    <div class="boards-wrap" id="bGrid"></div>
  </div>
  <div class="df">
    <button class="btn" onclick="document.getElementById('dlg').close()">取消</button>
    <button class="btn btn-g" onclick="save()">儲存</button>
  </div>
</dialog>

<script>
let boards=[], contacts={}, editing=null;

async function load(){
  [boards,contacts]=await Promise.all([
    fetch('/api/boards').then(r=>r.json()),
    fetch('/api/contacts').then(r=>r.json())
  ]);
  render();
}

function render(){
  const tb=document.getElementById('tb');
  const names=Object.keys(contacts);
  if(!names.length){tb.innerHTML='<tr><td colspan="4" class="empty">尚無聯絡人</td></tr>';return;}
  tb.innerHTML=names.map(n=>{
    const c=contacts[n];
    const proj=c.projects==='*'
      ?'<span class="badge ba">員工（全部）</span>'
      :(c.projects||[]).map(p=>`<span class="badge bp">${p}</span>`).join('')||'—';
    return `<tr>
      <td>${n}</td>
      <td style="font-family:monospace;font-size:12px;color:#aaa">${c.line_id}</td>
      <td>${proj}</td>
      <td>
        <button class="btn btn-b" onclick="openEdit('${n}')">編輯</button>
        <button class="btn btn-r" onclick="del('${n}')">刪除</button>
      </td>
    </tr>`;
  }).join('');
}

function toggleB(show){document.getElementById('bField').style.display=show?'':'none';}

function renderGrid(sel){
  document.getElementById('bGrid').innerHTML=boards.map(b=>{
    const on=sel.includes(b);
    return `<span class="chip ${on?'on':''}" onclick="this.classList.toggle('on')">${b}</span>`;
  }).join('');
}

function openAdd(){
  editing=null;
  document.getElementById('dlgT').textContent='新增聯絡人';
  document.getElementById('fN').value='';
  document.getElementById('fL').value='';
  document.querySelector('input[name=pt][value=all]').checked=true;
  toggleB(false); renderGrid([]);
  document.getElementById('dlg').showModal();
}

function openEdit(n){
  editing=n;
  const c=contacts[n];
  document.getElementById('dlgT').textContent='編輯聯絡人';
  document.getElementById('fN').value=n;
  document.getElementById('fL').value=c.line_id;
  const isAll=c.projects==='*';
  document.querySelector(`input[name=pt][value=${isAll?'all':'sel'}]`).checked=true;
  toggleB(!isAll); renderGrid(isAll?[]:(c.projects||[]));
  document.getElementById('dlg').showModal();
}

async function save(){
  const name=document.getElementById('fN').value.trim();
  const lid=document.getElementById('fL').value.trim();
  if(!name||!lid){alert('請填寫姓名和 LINE ID');return;}
  const isAll=document.querySelector('input[name=pt]:checked').value==='all';
  const projects=isAll?'*':[...document.querySelectorAll('#bGrid .chip.on')].map(e=>e.textContent.trim());
  const body={name,line_id:lid,projects};
  const url=editing?`/api/contacts/${encodeURIComponent(editing)}`:'/api/contacts';
  const res=await fetch(url,{method:editing?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await res.json();
  if(!res.ok){alert(d.error);return;}
  document.getElementById('dlg').close();
  await load();
}

async function del(n){
  if(!confirm(`確定刪除「${n}」？`))return;
  await fetch(`/api/contacts/${encodeURIComponent(n)}`,{method:'DELETE'});
  await load();
}

load();
</script>
</body>
</html>"""


@app.get("/")
@require_auth
def index():
    return HTML


@app.get("/health")
def health():
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081, debug=False)
