#!/usr/bin/env python3
"""
Admin Web UI — 聯絡人 & 工地權限管理

GET  /                      HTML 管理介面
GET  /api/contacts          列出所有聯絡人
POST /api/contacts          新增
PUT  /api/contacts/<name>   更新
DELETE /api/contacts/<name> 刪除
GET  /api/boards            Trello 看板清單（from DB）
GET  /api/users             LINE 用戶列表（支援 ?role= 篩選）
PUT  /api/users/<line_id>   更新角色與專案
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
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT board_name FROM trello_boards ORDER BY board_name")
            return cur.fetchall()
    rows = db_exec(_q) or []
    return jsonify([r[0] if not isinstance(r, dict) else r["board_name"] for r in rows])


# ── Users API ─────────────────────────────────────────────────────────────────

@app.get("/api/users")
@require_auth
def list_users():
    role_filter = request.args.get("role")

    def _q(conn):
        with conn.cursor() as cur:
            if role_filter:
                cur.execute(
                    "SELECT line_id, display_name, picture_url, role, projects, "
                    "created_at, updated_at FROM line_users WHERE role = %s "
                    "ORDER BY created_at DESC",
                    (role_filter,),
                )
            else:
                cur.execute(
                    "SELECT line_id, display_name, picture_url, role, projects, "
                    "created_at, updated_at FROM line_users ORDER BY created_at DESC"
                )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    rows = db_exec(_q) or []
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
        if r.get("updated_at"):
            r["updated_at"] = r["updated_at"].isoformat()
    return jsonify(rows)


@app.put("/api/users/<line_id>")
@require_auth
def update_user(line_id: str):
    body = request.get_json() or {}
    new_role = body.get("role")
    new_projects = body.get("projects")

    valid_roles = {"admin", "employee", "vendor", "customer", "visitor"}
    if new_role and new_role not in valid_roles:
        return jsonify({"error": f"invalid role: {new_role}"}), 400

    auth_user = request.authorization
    if new_role == "admin":
        def _check_caller(conn):
            with conn.cursor() as cur:
                cur.execute("SELECT role FROM line_users WHERE display_name = %s", (auth_user.username,))
                row = cur.fetchone()
                return row[0] if row else None
        caller_role = db_exec(_check_caller)
        if caller_role != "admin":
            return jsonify({"error": "only admin can assign admin role"}), 403

    def _update(conn, _lid=line_id, _role=new_role, _projects=new_projects):
        with conn.cursor() as cur:
            if _role is not None and _projects is not None:
                cur.execute(
                    "UPDATE line_users SET role=%s, projects=%s::jsonb, updated_at=now() "
                    "WHERE line_id=%s",
                    (_role, json.dumps(_projects), _lid),
                )
            elif _role is not None:
                cur.execute(
                    "UPDATE line_users SET role=%s, updated_at=now() WHERE line_id=%s",
                    (_role, _lid),
                )
            elif _projects is not None:
                cur.execute(
                    "UPDATE line_users SET projects=%s::jsonb, updated_at=now() WHERE line_id=%s",
                    (json.dumps(_projects), _lid),
                )
            return cur.rowcount

    rows = db_exec(_update)
    if not rows:
        return jsonify({"error": "not found"}), 404
    log.info(f"[admin] Updated user {line_id[:8]} role={new_role}")
    return jsonify({"ok": True})


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
nav{background:#fff;border-bottom:1px solid #eee;display:flex;gap:0;padding:0 24px}
nav button{padding:12px 20px;border:none;background:none;cursor:pointer;font-size:14px;color:#666;border-bottom:2px solid transparent}
nav button.active{color:#06c755;border-bottom-color:#06c755;font-weight:600}
main{max-width:1000px;margin:24px auto;padding:0 16px}
.card{background:#fff;border-radius:8px;box-shadow:0 1px 4px #0001;padding:20px;margin-bottom:20px}
h2{font-size:13px;font-weight:600;margin-bottom:16px;color:#888;text-transform:uppercase;letter-spacing:.5px}
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:12px;color:#999;padding:8px 12px;border-bottom:2px solid #eee}
td{padding:10px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}
tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:2px 9px;border-radius:12px;font-size:12px;margin:2px}
.ba{background:#e8f5e9;color:#2e7d32}.bp{background:#e3f2fd;color:#1565c0}
.br{background:#fce4ec;color:#b71c1c}.bo{background:#fff3e0;color:#e65100}
.bg{background:#f3e5f5;color:#6a1b9a}.bv{background:#f5f5f5;color:#757575}
.btn{padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:500}
.btn-g{background:#06c755;color:#fff}.btn-r{background:#fff;color:#e53935;border:1px solid #e53935}
.btn-b{background:#fff;color:#1976d2;border:1px solid #1976d2}.btn+.btn{margin-left:6px}
dialog{border:none;border-radius:12px;padding:24px;width:520px;max-width:95vw;box-shadow:0 8px 32px #0003}
dialog::backdrop{background:#0005}
dialog h3{margin-bottom:18px;font-size:16px}
.field{margin-bottom:14px}
label.lbl{display:block;font-size:13px;color:#666;margin-bottom:5px}
input[type=text],select{width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:14px}
input[type=text]:focus,select:focus{outline:none;border-color:#06c755}
.radio-row{display:flex;gap:20px;margin-bottom:14px;flex-wrap:wrap}
.radio-row label{font-size:13px;display:flex;align-items:center;gap:6px;cursor:pointer}
.boards-wrap{border:1px solid #ddd;border-radius:6px;padding:10px;max-height:180px;overflow-y:auto;display:flex;flex-wrap:wrap;gap:6px}
.chip{padding:5px 12px;border-radius:16px;background:#f0f0f0;font-size:13px;cursor:pointer;user-select:none;border:1px solid transparent}
.chip.on{background:#e3f2fd;color:#1565c0;border-color:#90caf9}
.df{display:flex;justify-content:flex-end;gap:8px;margin-top:20px}
.empty{text-align:center;padding:32px;color:#bbb;font-size:14px}
.avatar{width:32px;height:32px;border-radius:50%;background:#eee;object-fit:cover;vertical-align:middle}
.filter-row{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.filter-row select{width:auto;min-width:120px}
.tab{display:none}.tab.active{display:block}
#addBtn{margin-bottom:14px}
</style>
</head>
<body>
<header>
  <svg width="26" height="26" viewBox="0 0 24 24" fill="white"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>
  <h1>LINE 客服管理</h1>
</header>
<nav>
  <button class="active" onclick="switchTab('users')">用戶管理</button>
  <button onclick="switchTab('contacts')">聯絡人（舊）</button>
</nav>
<main>

<div id="tabUsers" class="tab active">
  <div class="card">
    <h2>LINE 用戶</h2>
    <div class="filter-row">
      <select id="roleFilter" onchange="loadUsers()">
        <option value="">全部角色</option>
        <option value="visitor">訪客</option>
        <option value="customer">客戶</option>
        <option value="vendor">合作廠商</option>
        <option value="employee">員工</option>
        <option value="admin">管理員</option>
      </select>
      <button class="btn btn-b" onclick="loadUsers()">重新整理</button>
    </div>
    <table>
      <thead><tr><th>頭貼</th><th>顯示名稱</th><th>LINE ID</th><th>角色</th><th>可存取專案</th><th>建立時間</th><th>操作</th></tr></thead>
      <tbody id="utb"><tr><td colspan="7" class="empty">載入中…</td></tr></tbody>
    </table>
  </div>
</div>

<div id="tabContacts" class="tab">
  <div class="card">
    <h2>聯絡人 / 工地權限（contacts.json）</h2>
    <button class="btn btn-g" id="addBtn" onclick="openAdd()">＋ 新增聯絡人</button>
    <table>
      <thead><tr><th>姓名</th><th>LINE User ID</th><th>工地權限</th><th>操作</th></tr></thead>
      <tbody id="tb"><tr><td colspan="4" class="empty">載入中…</td></tr></tbody>
    </table>
  </div>
</div>

</main>

<dialog id="udlg">
  <h3>編輯用戶</h3>
  <div class="field"><label class="lbl">顯示名稱</label><input type="text" id="uName" readonly style="background:#f9f9f9"></div>
  <div class="field"><label class="lbl">LINE ID</label><input type="text" id="uId" readonly style="background:#f9f9f9;font-size:12px"></div>
  <div class="field">
    <label class="lbl">角色</label>
    <select id="uRole" onchange="toggleUBoards()">
      <option value="visitor">訪客</option>
      <option value="customer">客戶</option>
      <option value="vendor">合作廠商</option>
      <option value="employee">員工</option>
      <option value="admin">管理員</option>
    </select>
  </div>
  <div class="field" id="ubField">
    <label class="lbl">可存取的工地（點選切換）</label>
    <div class="boards-wrap" id="ubGrid"></div>
  </div>
  <div class="df">
    <button class="btn" onclick="document.getElementById('udlg').close()">取消</button>
    <button class="btn btn-g" onclick="saveUser()">儲存</button>
  </div>
</dialog>

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
/* esc() HTML-encodes all user-supplied data before DOM insertion to prevent XSS */
function esc(s){
  const d=document.createElement('div');
  d.appendChild(document.createTextNode(s==null?'':String(s)));
  return d.innerHTML;
}

const ROLE_LABEL={admin:'管理員',employee:'員工',vendor:'合作廠商',customer:'客戶',visitor:'訪客'};
const ROLE_CLS={admin:'br',employee:'ba',vendor:'bo',customer:'bp',visitor:'bv'};
let boards=[], contacts={}, editing=null, editingUid=null;

function switchTab(t){
  document.querySelectorAll('nav button').forEach((b,i)=>b.classList.toggle('active',['users','contacts'][i]===t));
  document.querySelectorAll('.tab').forEach(el=>el.classList.remove('active'));
  const id='tab'+t.charAt(0).toUpperCase()+t.slice(1);
  document.getElementById(id).classList.add('active');
  if(t==='contacts'&&!Object.keys(contacts).length) loadContacts();
}

/* ── Users ── */

async function loadUsers(){
  const role=document.getElementById('roleFilter').value;
  const url='/api/users'+(role?'?role='+encodeURIComponent(role):'');
  const users=await fetch(url).then(r=>r.json()).catch(()=>[]);
  renderUsers(users);
}

function renderUsers(users){
  const tb=document.getElementById('utb');
  if(!users.length){tb.textContent='';const tr=tb.insertRow();const td=tr.insertCell();td.colSpan=7;td.className='empty';td.textContent='無資料';return;}
  tb.textContent='';
  users.forEach(u=>{
    const tr=tb.insertRow();
    const avatar=tr.insertCell(); avatar.style.width='44px';
    if(u.picture_url){const img=document.createElement('img');img.className='avatar';img.src=u.picture_url;img.onerror=()=>img.remove();avatar.appendChild(img);}
    else{const div=document.createElement('div');div.className='avatar';avatar.appendChild(div);}

    const tdName=tr.insertCell(); tdName.textContent=u.display_name||'（未知）';
    const tdId=tr.insertCell(); tdId.style.cssText='font-family:monospace;font-size:11px;color:#aaa';
    tdId.textContent=(u.line_id||'').substring(0,8)+'…';

    const tdRole=tr.insertCell();
    const badge=document.createElement('span');
    badge.className='badge '+(ROLE_CLS[u.role]||'bv');
    badge.textContent=ROLE_LABEL[u.role]||u.role;
    tdRole.appendChild(badge);

    const tdProj=tr.insertCell();
    (u.projects||[]).forEach(p=>{const s=document.createElement('span');s.className='badge bp';s.textContent=p;tdProj.appendChild(s);});
    if(!(u.projects||[]).length) tdProj.textContent='—';

    const tdDate=tr.insertCell(); tdDate.style.cssText='font-size:12px;color:#aaa';
    tdDate.textContent=u.created_at?u.created_at.substring(0,10):'—';

    const tdAct=tr.insertCell();
    const btn=document.createElement('button');
    btn.className='btn btn-b'; btn.textContent='編輯';
    btn.onclick=()=>openEditUser(u);
    tdAct.appendChild(btn);
  });
}

async function openEditUser(u){
  if(!boards.length) boards=await fetch('/api/boards').then(r=>r.json()).catch(()=>[]);
  editingUid=u.line_id;
  document.getElementById('uName').value=u.display_name||'';
  document.getElementById('uId').value=u.line_id||'';
  document.getElementById('uRole').value=u.role||'visitor';
  toggleUBoards();
  renderUGrid(u.projects||[]);
  document.getElementById('udlg').showModal();
}

function toggleUBoards(){
  const r=document.getElementById('uRole').value;
  document.getElementById('ubField').style.display=(r==='vendor'||r==='customer')?'':'none';
}

function renderUGrid(sel){
  const wrap=document.getElementById('ubGrid');
  wrap.textContent='';
  boards.forEach(b=>{
    const chip=document.createElement('span');
    chip.className='chip'+(sel.includes(b)?' on':'');
    chip.textContent=b;
    chip.onclick=()=>chip.classList.toggle('on');
    wrap.appendChild(chip);
  });
}

async function saveUser(){
  const role=document.getElementById('uRole').value;
  const projects=[...document.querySelectorAll('#ubGrid .chip.on')].map(e=>e.textContent.trim());
  const body={role,projects:(role==='vendor'||role==='customer')?projects:[]};
  const res=await fetch('/api/users/'+encodeURIComponent(editingUid),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await res.json();
  if(!res.ok){alert(d.error);return;}
  document.getElementById('udlg').close();
  loadUsers();
}

/* ── Contacts ── */

async function loadContacts(){
  [boards,contacts]=await Promise.all([
    fetch('/api/boards').then(r=>r.json()),
    fetch('/api/contacts').then(r=>r.json())
  ]);
  renderContacts();
}

function renderContacts(){
  const tb=document.getElementById('tb');
  const names=Object.keys(contacts);
  if(!names.length){tb.textContent='';const tr=tb.insertRow();const td=tr.insertCell();td.colSpan=4;td.className='empty';td.textContent='尚無聯絡人';return;}
  tb.textContent='';
  names.forEach(n=>{
    const c=contacts[n];
    const tr=tb.insertRow();
    tr.insertCell().textContent=n;
    const tdId=tr.insertCell(); tdId.style.cssText='font-family:monospace;font-size:12px;color:#aaa'; tdId.textContent=c.line_id;
    const tdP=tr.insertCell();
    if(c.projects==='*'){const s=document.createElement('span');s.className='badge ba';s.textContent='員工（全部）';tdP.appendChild(s);}
    else{(c.projects||[]).forEach(p=>{const s=document.createElement('span');s.className='badge bp';s.textContent=p;tdP.appendChild(s);});if(!(c.projects||[]).length)tdP.textContent='—';}
    const tdAct=tr.insertCell();
    const eb=document.createElement('button');eb.className='btn btn-b';eb.textContent='編輯';eb.onclick=()=>openEdit(n);tdAct.appendChild(eb);
    const db2=document.createElement('button');db2.className='btn btn-r';db2.style.marginLeft='6px';db2.textContent='刪除';db2.onclick=()=>del(n);tdAct.appendChild(db2);
  });
}

function toggleB(show){document.getElementById('bField').style.display=show?'':'none';}

function renderGrid(sel){
  const wrap=document.getElementById('bGrid');
  wrap.textContent='';
  boards.forEach(b=>{
    const chip=document.createElement('span');
    chip.className='chip'+(sel.includes(b)?' on':'');
    chip.textContent=b;
    chip.onclick=()=>chip.classList.toggle('on');
    wrap.appendChild(chip);
  });
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
  document.querySelector('input[name=pt][value='+(isAll?'all':'sel')+']').checked=true;
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
  const url=editing?'/api/contacts/'+encodeURIComponent(editing):'/api/contacts';
  const res=await fetch(url,{method:editing?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await res.json();
  if(!res.ok){alert(d.error);return;}
  document.getElementById('dlg').close();
  loadContacts();
}

async function del(n){
  if(!confirm('確定刪除「'+n+'」？'))return;
  await fetch('/api/contacts/'+encodeURIComponent(n),{method:'DELETE'});
  loadContacts();
}

loadUsers();
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
