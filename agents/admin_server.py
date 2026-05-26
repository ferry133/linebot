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
import shutil
import functools
import logging
import datetime

from flask import Flask, request, jsonify, Response
from shared.log import setup as _setup_log
from shared.db import db_exec, run_migrations

_setup_log()
log = logging.getLogger(__name__)

run_migrations()

app = Flask(__name__)

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge")
CONTACTS_FILE = os.path.join(KNOWLEDGE_DIR, "contacts.json")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "changeme")

NAS_MOUNT_PATH = os.environ.get("NAS_MOUNT_PATH", "/mnt/nas/jia.homedesign")
NAS_ACTIVE_PATH = os.path.join(NAS_MOUNT_PATH, "00. 執行中案場")
NAS_TEMPLATE_PATH = os.environ.get(
    "NAS_TEMPLATE_PATH",
    os.path.join(NAS_MOUNT_PATH, "C.公司SOP表單 and Check list/01.新開案資料夾：電腦檔案資料夾編號順序01.02.03"),
)


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
            cur.execute("SELECT board_id, board_name FROM trello_boards ORDER BY board_name")
            return cur.fetchall()
    rows = db_exec(_q) or []
    return jsonify([{"board_id": r[0], "board_name": r[1]} for r in rows])


# ── Users API ─────────────────────────────────────────────────────────────────

@app.get("/api/users")
@require_auth
def list_users():
    role_filter = request.args.get("role")

    def _q(conn):
        with conn.cursor() as cur:
            if role_filter:
                cur.execute(
                    "SELECT line_id, display_name, picture_url, role, alias_name, "
                    "created_at, updated_at FROM line_users WHERE role = %s "
                    "ORDER BY created_at DESC",
                    (role_filter,),
                )
            else:
                cur.execute(
                    "SELECT line_id, display_name, picture_url, role, alias_name, "
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
    new_alias = body.get("alias_name", ...)  # sentinel to detect presence

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

    alias_in_body = "alias_name" in body
    alias_value = body.get("alias_name") if alias_in_body else None
    alias_normalized = (alias_value or "").strip().lower() or None if alias_in_body else None

    if alias_in_body and alias_normalized:
        def _check_alias(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT line_id FROM line_users WHERE alias_name=%s AND line_id!=%s",
                    (alias_normalized, line_id),
                )
                return cur.fetchone()
        if db_exec(_check_alias):
            return jsonify({"error": "此簡稱已被使用"}), 409

    def _update(conn, _lid=line_id, _role=new_role):
        with conn.cursor() as cur:
            parts = []
            params = []
            if _role is not None:
                parts.append("role=%s")
                params.append(_role)
            if alias_in_body:
                parts.append("alias_name=%s")
                params.append(alias_normalized)
            if not parts:
                return 0
            parts.append("updated_at=now()")
            params.append(_lid)
            sql = "UPDATE line_users SET " + ", ".join(parts) + " WHERE line_id=%s"
            cur.execute(sql, params)
            return cur.rowcount

    rows = db_exec(_update)
    if not rows:
        return jsonify({"error": "not found"}), 404
    log.info("[admin] Updated user %s role=%s", line_id[:8], new_role)

    def _clear_memory(conn, _lid=line_id):
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM working_memory WHERE agent_id='customer_service' AND thread_id=%s",
                (_lid,),
            )
    db_exec(_clear_memory)

    return jsonify({"ok": True})


# ── Projects helpers ──────────────────────────────────────────────────────────

def _generate_case_number(year: int) -> str:
    roc_year = year - 1911
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT max((regexp_match(case_number, '(\\d+)案$'))[1]::int) "
                "FROM projects WHERE case_number LIKE %s",
                (f"{roc_year}年%",),
            )
            row = cur.fetchone()
            return (row[0] or 0) + 1
    seq = db_exec(_q) or 1
    return f"{roc_year}年第{seq}案"


def _provision_nas_folder(folder_name: str):
    if not os.path.exists(NAS_TEMPLATE_PATH):
        log.warning("[admin] NAS template not found: %s", NAS_TEMPLATE_PATH)
        return None, "template not found"
    dest = os.path.join(NAS_ACTIVE_PATH, folder_name)
    if os.path.exists(dest):
        log.warning("[admin] NAS folder already exists: %s", dest)
        return None, "folder exists"
    try:
        shutil.copytree(NAS_TEMPLATE_PATH, dest)
        log.info("[admin] NAS folder provisioned: %s", dest)
        return dest, None
    except Exception as e:
        log.warning("[admin] NAS copytree failed: %s", e)
        return None, str(e)


# ── NAS folders ───────────────────────────────────────────────────────────────

@app.get("/api/nas/folders")
@require_auth
def list_nas_folders():
    unassigned = request.args.get("unassigned") in ("1", "true", "yes")
    try:
        names = sorted(
            n for n in os.listdir(NAS_ACTIVE_PATH)
            if not n.startswith(".") and os.path.isdir(os.path.join(NAS_ACTIVE_PATH, n))
        )
    except OSError as e:
        return jsonify({"error": str(e), "base": NAS_ACTIVE_PATH, "folders": []}), 200
    if unassigned:
        def _q(conn):
            with conn.cursor() as cur:
                cur.execute("SELECT nas_path FROM projects WHERE nas_path IS NOT NULL")
                return {row[0] for row in cur.fetchall()}
        used = db_exec(_q) or set()
        names = [n for n in names if os.path.join(NAS_ACTIVE_PATH, n) not in used]
    return jsonify({"base": NAS_ACTIVE_PATH, "folders": names})


# ── Projects API ──────────────────────────────────────────────────────────────

@app.get("/api/projects")
@require_auth
def list_projects():
    status_filter = request.args.get("status")
    year_filter = request.args.get("year")

    def _q(conn):
        with conn.cursor() as cur:
            sql = (
                "SELECT p.project_id, p.case_number, p.name, p.trello_board_id, "
                "tb.board_name, p.nas_path, p.status, p.notes, p.started_at, "
                "p.completed_at, p.created_at, p.updated_at, "
                "count(lup.line_id) AS member_count "
                "FROM projects p "
                "LEFT JOIN trello_boards tb ON tb.board_id = p.trello_board_id "
                "LEFT JOIN line_user_projects lup ON lup.project_id = p.project_id "
                "WHERE 1=1"
            )
            params = []
            if status_filter:
                sql += " AND p.status = %s"
                params.append(status_filter)
            if year_filter:
                roc_year = int(year_filter) - 1911
                sql += " AND p.case_number LIKE %s"
                params.append(f"{roc_year}年%")
            sql += " GROUP BY p.project_id, tb.board_name ORDER BY p.created_at DESC"
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    rows = db_exec(_q) or []
    for r in rows:
        for k in ("created_at", "updated_at"):
            if r.get(k):
                r[k] = r[k].isoformat()
        for k in ("started_at", "completed_at"):
            if r.get(k):
                r[k] = r[k].isoformat()
        if r.get("project_id"):
            r["project_id"] = str(r["project_id"])
    return jsonify(rows)


@app.post("/api/projects")
@require_auth
def create_project():
    body = request.get_json() or {}
    name = (body.get("name") or "").strip()
    case_number = (body.get("case_number") or "").strip()
    trello_board_id = (body.get("trello_board_id") or None)
    notes = body.get("notes")
    import_existing = bool(body.get("import_existing"))

    if not name:
        return jsonify({"error": "name is required"}), 400

    nas_path = None
    if import_existing:
        if not case_number:
            return jsonify({"error": "case_number (folder) is required for import"}), 400
        candidate = case_number if case_number.startswith("/") else os.path.join(NAS_ACTIVE_PATH, case_number)
        if not candidate.startswith(NAS_MOUNT_PATH):
            return jsonify({"error": f"路徑須位於 {NAS_MOUNT_PATH} 之下"}), 400
        if not os.path.isdir(candidate):
            return jsonify({"error": f"資料夾不存在：{candidate}"}), 400
        nas_path = candidate
        if case_number.startswith("/"):
            case_number = os.path.basename(case_number.rstrip("/"))
    else:
        if not case_number:
            case_number = _generate_case_number(datetime.date.today().year)
        nas_path, nas_warning = _provision_nas_folder(case_number)
        if nas_warning == "folder exists":
            return jsonify({"error": "NAS folder already exists", "folder": case_number}), 409

    def _insert(conn):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO projects (case_number, name, trello_board_id, nas_path, notes) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING project_id",
                (case_number, name, trello_board_id, nas_path, notes),
            )
            return str(cur.fetchone()[0])

    project_id = db_exec(_insert)
    if not project_id:
        return jsonify({"error": "DB insert failed"}), 500

    log.info("[admin] Created project %s: %s", case_number, name)
    resp = {"ok": True, "project_id": project_id, "case_number": case_number, "nas_path": nas_path}
    if nas_warning:
        resp["nas_warning"] = nas_warning
    return jsonify(resp), 201


@app.get("/api/projects/<project_id>")
@require_auth
def get_project(project_id: str):
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT p.project_id, p.case_number, p.name, p.trello_board_id, "
                "tb.board_name, p.nas_path, p.status, p.notes, p.started_at, "
                "p.completed_at, p.created_at, p.updated_at "
                "FROM projects p "
                "LEFT JOIN trello_boards tb ON tb.board_id = p.trello_board_id "
                "WHERE p.project_id = %s::uuid",
                (project_id,),
            )
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            return dict(zip(cols, row)) if row else None

    r = db_exec(_q)
    if not r:
        return jsonify({"error": "not found"}), 404
    for k in ("created_at", "updated_at", "started_at", "completed_at"):
        if r.get(k):
            r[k] = r[k].isoformat()
    r["project_id"] = str(r["project_id"])
    return jsonify(r)


@app.put("/api/projects/<project_id>")
@require_auth
def update_project(project_id: str):
    body = request.get_json() or {}
    allowed = {"name", "trello_board_id", "status", "notes", "nas_path"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return jsonify({"error": "no valid fields"}), 400

    valid_statuses = {"active", "completed", "archived"}
    if "status" in updates and updates["status"] not in valid_statuses:
        return jsonify({"error": f"invalid status: {updates['status']}"}), 400

    if "nas_path" in updates:
        new_nas = (updates["nas_path"] or "").strip() or None
        if new_nas:
            if not new_nas.startswith(NAS_MOUNT_PATH):
                return jsonify({"error": f"nas_path 必須位於 {NAS_MOUNT_PATH} 之下"}), 400
            if not os.path.isdir(new_nas):
                return jsonify({"error": f"資料夾不存在：{new_nas}"}), 400
        updates["nas_path"] = new_nas

    def _upd(conn):
        with conn.cursor() as cur:
            set_parts = [f"{k} = %s" for k in updates]
            params = list(updates.values())
            if updates.get("status") == "archived":
                set_parts.append("completed_at = now()")
            set_parts.append("updated_at = now()")
            sql = "UPDATE projects SET " + ", ".join(set_parts) + " WHERE project_id = %s::uuid"
            params.append(project_id)
            cur.execute(sql, params)
            return cur.rowcount

    rows = db_exec(_upd)
    if not rows:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})


# ── Project-User Assignment API ───────────────────────────────────────────────

@app.get("/api/projects/<project_id>/users")
@require_auth
def get_project_users(project_id: str):
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT lup.line_id, lu.display_name, lu.picture_url, lup.relation "
                "FROM line_user_projects lup "
                "JOIN line_users lu ON lu.line_id = lup.line_id "
                "WHERE lup.project_id = %s::uuid ORDER BY lup.created_at",
                (project_id,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    return jsonify(db_exec(_q) or [])


@app.put("/api/projects/<project_id>/users")
@require_auth
def assign_project_users(project_id: str):
    body = request.get_json() or {}
    members = body.get("members", [])

    def _upd(conn):
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM line_user_projects WHERE project_id = %s::uuid",
                (project_id,),
            )
            for m in members:
                cur.execute(
                    "INSERT INTO line_user_projects (line_id, project_id, relation) "
                    "VALUES (%s, %s::uuid, %s) "
                    "ON CONFLICT (line_id, project_id) DO UPDATE SET relation=EXCLUDED.relation",
                    (m["line_id"], project_id, m.get("relation", "customer")),
                )
            return len(members)

    db_exec(_upd)
    return jsonify({"ok": True})


@app.get("/api/users/<line_id>/projects")
@require_auth
def get_user_projects(line_id: str):
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT p.project_id, p.case_number, p.name, p.status, lup.relation "
                "FROM line_user_projects lup "
                "JOIN projects p ON p.project_id = lup.project_id "
                "WHERE lup.line_id = %s ORDER BY p.created_at DESC",
                (line_id,),
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            for r in rows:
                r["project_id"] = str(r["project_id"])
            return rows

    return jsonify(db_exec(_q) or [])


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
main{max-width:1100px;margin:24px auto;padding:0 16px}
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
.bal{background:#eeeeee;color:#555;font-size:11px}
.btn{padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:500}
.btn-g{background:#06c755;color:#fff}.btn-r{background:#fff;color:#e53935;border:1px solid #e53935}
.btn-b{background:#fff;color:#1976d2;border:1px solid #1976d2}.btn+.btn{margin-left:6px}
dialog{border:none;border-radius:12px;padding:24px;width:560px;max-width:95vw;box-shadow:0 8px 32px #0003}
dialog::backdrop{background:#0005}
dialog h3{margin-bottom:18px;font-size:16px}
.field{margin-bottom:14px}
label.lbl{display:block;font-size:13px;color:#666;margin-bottom:5px}
input[type=text],select,textarea{width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:14px}
input[type=text]:focus,select:focus,textarea:focus{outline:none;border-color:#06c755}
.hint{font-size:11px;color:#999;margin-top:4px}
.radio-row{display:flex;gap:20px;margin-bottom:14px;flex-wrap:wrap}
.radio-row label{font-size:13px;display:flex;align-items:center;gap:6px;cursor:pointer}
.boards-wrap{border:1px solid #ddd;border-radius:6px;padding:10px;max-height:180px;overflow-y:auto;display:flex;flex-wrap:wrap;gap:6px}
.chip{padding:5px 12px;border-radius:16px;background:#f0f0f0;font-size:13px;cursor:pointer;user-select:none;border:1px solid transparent}
.chip.on{background:#e3f2fd;color:#1565c0;border-color:#90caf9}
.df{display:flex;justify-content:flex-end;gap:8px;margin-top:20px}
.empty{text-align:center;padding:32px;color:#bbb;font-size:14px}
.avatar{width:32px;height:32px;border-radius:50%;background:#eee;object-fit:cover;vertical-align:middle}
.filter-row{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;align-items:center}
.filter-row select{width:auto;min-width:120px}
.tab{display:none}.tab.active{display:block}
#addBtn{margin-bottom:14px}
.proj-row td{font-size:13px}
.status-active{color:#2e7d32}.status-archived{color:#999}.status-completed{color:#1565c0}
.members-section{padding:12px 0 0;border-top:1px solid #f0f0f0;margin-top:8px}
.member-chip{display:inline-flex;align-items:center;gap:6px;background:#f0f0f0;border-radius:16px;padding:4px 10px;font-size:12px;margin:2px}
.member-chip .remove{cursor:pointer;color:#e53935;font-weight:700}
</style>
</head>
<body>
<header>
  <svg width="26" height="26" viewBox="0 0 24 24" fill="white"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>
  <h1>LINE 客服管理</h1>
</header>
<nav>
  <button class="active" onclick="switchTab('users')">用戶管理</button>
  <button onclick="switchTab('projects')">專案管理</button>
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
      <thead><tr><th>頭貼</th><th>顯示名稱</th><th>簡稱</th><th>LINE ID</th><th>角色</th><th>建立時間</th><th>操作</th></tr></thead>
      <tbody id="utb"><tr><td colspan="6" class="empty">載入中…</td></tr></tbody>
    </table>
  </div>
</div>

<div id="tabProjects" class="tab">
  <div class="card">
    <h2>專案列表</h2>
    <div class="filter-row">
      <select id="projStatusFilter" onchange="loadProjects()">
        <option value="">全部狀態</option>
        <option value="active">進行中</option>
        <option value="completed">已完成</option>
        <option value="archived">已封存</option>
      </select>
      <button class="btn btn-g" onclick="openAddProject()">＋ 新增專案</button>
      <button class="btn btn-b" onclick="openImportProject()" style="margin-left:8px">↳ 匯入既有專案</button>
      <button class="btn btn-b" onclick="loadProjects()">重新整理</button>
    </div>
    <table>
      <thead><tr><th>案號</th><th>名稱</th><th>Trello 看板</th><th>NAS 路徑</th><th>狀態</th><th>人員數</th><th>操作</th></tr></thead>
      <tbody id="ptb"><tr><td colspan="7" class="empty">載入中…</td></tr></tbody>
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

<!-- User edit dialog -->
<dialog id="udlg">
  <h3>編輯用戶</h3>
  <div class="field"><label class="lbl">顯示名稱</label><input type="text" id="uName" readonly style="background:#f9f9f9"></div>
  <div class="field"><label class="lbl">LINE ID</label><input type="text" id="uId" readonly style="background:#f9f9f9;font-size:12px"></div>
  <div class="field">
    <label class="lbl">alias_name（簡稱）</label>
    <input type="text" id="uAlias" placeholder="larry、sa、yan…">
    <p class="hint">用於 Trello 標記，設定後請避免變更</p>
  </div>
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
    <label class="lbl">可存取的專案（點選切換）</label>
    <div class="boards-wrap" id="ubGrid"></div>
  </div>
  <div class="df">
    <button class="btn" onclick="document.getElementById('udlg').close()">取消</button>
    <button class="btn btn-g" onclick="saveUser()">儲存</button>
  </div>
</dialog>

<!-- Add/edit project dialog -->
<dialog id="pdlg">
  <h3 id="pdlgT">新增專案</h3>
  <div class="field"><label class="lbl">專案名稱</label><input type="text" id="pName" placeholder="XX 公館裝修工程"></div>
  <div class="field" id="pFolderField"><label class="lbl">案號（即 NAS 資料夾名）</label>
    <input type="text" id="pFolder" placeholder="留空自動生成 115年第N案">
    <div id="pFolderSelectWrap" style="display:none;align-items:center;gap:6px">
      <span id="pFolderBase" style="font-size:11px;color:#888;white-space:nowrap"></span>
      <span style="color:#888">/</span>
      <select id="pFolderSelect" style="font-size:12px;flex:1"><option value="">（無）</option></select>
    </div>
    <p class="hint">案號將作為 NAS 資料夾名建立於「00. 執行中案場/」下；可自訂如 115-001-XX公館</p></div>
  <div class="field">
    <label class="lbl">Trello 看板</label>
    <select id="pBoard"><option value="">（不指定）</option></select>
  </div>
  <div class="field"><label class="lbl">備註</label><textarea id="pNotes" rows="2"></textarea></div>
  <!-- Edit-only fields -->
  <div id="pEditFields" style="display:none">
    <div class="field"><label class="lbl">NAS 路徑</label>
      <div style="display:flex;align-items:center;gap:6px">
        <span id="pNasBase" style="font-size:11px;color:#888;white-space:nowrap"></span>
        <span style="color:#888">/</span>
        <select id="pNasPath" style="font-size:12px;flex:1"><option value="">（無）</option></select>
      </div>
      <div id="pNasHint" style="font-size:11px;color:#888;margin-top:4px"></div></div>
    <div class="field">
      <label class="lbl">狀態</label>
      <select id="pStatus">
        <option value="active">進行中</option>
        <option value="completed">已完成</option>
        <option value="archived">已封存</option>
      </select>
    </div>
  </div>
  <div class="df">
    <button class="btn" onclick="document.getElementById('pdlg').close()">取消</button>
    <button class="btn btn-g" onclick="saveProject()">儲存</button>
  </div>
</dialog>

<!-- Project members dialog -->
<dialog id="mmdlg">
  <h3 id="mmdlgT">專案人員指派</h3>
  <div class="field">
    <label class="lbl">新增人員</label>
    <div style="display:flex;gap:8px">
      <select id="mmUser" style="flex:1"></select>
      <select id="mmRelation" style="width:120px">
        <option value="customer">客戶</option>
        <option value="vendor">廠商</option>
      </select>
      <button class="btn btn-g" onclick="addMember()">加入</button>
    </div>
  </div>
  <div class="field">
    <label class="lbl">目前人員</label>
    <div id="mmList" style="min-height:40px"></div>
  </div>
  <div class="df">
    <button class="btn" onclick="document.getElementById('mmdlg').close()">關閉</button>
    <button class="btn btn-g" onclick="saveMembers()">儲存</button>
  </div>
</dialog>

<!-- Contact add/edit dialog -->
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
function esc(s){
  const d=document.createElement('div');
  d.appendChild(document.createTextNode(s==null?'':String(s)));
  return d.innerHTML;
}

const ROLE_LABEL={admin:'管理員',employee:'員工',vendor:'合作廠商',customer:'客戶',visitor:'訪客'};
const ROLE_CLS={admin:'br',employee:'ba',vendor:'bo',customer:'bp',visitor:'bv'};
const STATUS_LABEL={active:'進行中',completed:'已完成',archived:'已封存'};
const STATUS_CLS={active:'ba',completed:'bp',archived:'bv'};
let boards=[], contacts={}, editing=null, editingUid=null;
let allProjects=[], editingPid=null, importMode=false, projectMembers=[], editingMmPid=null;
let nasFolders=[], nasBase='';
let allUsers=[];

function switchTab(t){
  document.querySelectorAll('nav button').forEach((b,i)=>b.classList.toggle('active',['users','projects','contacts'][i]===t));
  document.querySelectorAll('.tab').forEach(el=>el.classList.remove('active'));
  const id='tab'+t.charAt(0).toUpperCase()+t.slice(1);
  document.getElementById(id).classList.add('active');
  if(t==='contacts'&&!Object.keys(contacts).length) loadContacts();
  if(t==='projects') loadProjects();
}

/* ── Users ── */

async function loadUsers(){
  const role=document.getElementById('roleFilter').value;
  const url='/api/users'+(role?'?role='+encodeURIComponent(role):'');
  allUsers=await fetch(url).then(r=>r.json()).catch(()=>[]);
  renderUsers(allUsers);
}

function renderUsers(users){
  const tb=document.getElementById('utb');
  if(!users.length){tb.textContent='';const tr=tb.insertRow();const td=tr.insertCell();td.colSpan=6;td.className='empty';td.textContent='無資料';return;}
  tb.textContent='';
  users.forEach(u=>{
    const tr=tb.insertRow();
    const avatar=tr.insertCell(); avatar.style.width='44px';
    if(u.picture_url){const img=document.createElement('img');img.className='avatar';img.src=u.picture_url;img.onerror=()=>img.remove();avatar.appendChild(img);}
    else{const div=document.createElement('div');div.className='avatar';avatar.appendChild(div);}

    const tdName=tr.insertCell();
    tdName.textContent=u.display_name||'（未知）';

    const tdAlias=tr.insertCell();
    if(u.alias_name){
      const ab=document.createElement('span');ab.className='badge bal';ab.textContent=u.alias_name;
      tdAlias.appendChild(ab);
    } else {
      tdAlias.style.cssText='color:#666';
      tdAlias.textContent='—';
    }

    const tdId=tr.insertCell(); tdId.style.cssText='font-family:monospace;font-size:11px;color:#aaa';
    tdId.textContent=(u.line_id||'').substring(0,8)+'…';

    const tdRole=tr.insertCell();
    const badge=document.createElement('span');
    badge.className='badge '+(ROLE_CLS[u.role]||'bv');
    badge.textContent=ROLE_LABEL[u.role]||u.role;
    tdRole.appendChild(badge);

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
  if(!allProjects.length) allProjects=await fetch('/api/projects').then(r=>r.json()).catch(()=>[]);
  editingUid=u.line_id;
  document.getElementById('uName').value=u.display_name||'';
  document.getElementById('uId').value=u.line_id||'';
  document.getElementById('uAlias').value=u.alias_name||'';
  document.getElementById('uRole').value=u.role||'visitor';
  toggleUBoards();
  const userProjs=await fetch('/api/users/'+encodeURIComponent(u.line_id)+'/projects').then(r=>r.json()).catch(()=>[]);
  const selectedIds=userProjs.map(p=>p.project_id);
  renderUGrid(selectedIds);
  document.getElementById('udlg').showModal();
}

function toggleUBoards(){
  const r=document.getElementById('uRole').value;
  document.getElementById('ubField').style.display=(r==='vendor'||r==='customer')?'':'none';
}

function renderUGrid(selIds){
  const wrap=document.getElementById('ubGrid');
  wrap.textContent='';
  const active=allProjects.filter(p=>p.status==='active');
  active.forEach(p=>{
    const chip=document.createElement('span');
    chip.className='chip'+(selIds.includes(p.project_id)?' on':'');
    chip.textContent=p.case_number+' '+p.name;
    chip.dataset.pid=p.project_id;
    chip.onclick=()=>chip.classList.toggle('on');
    wrap.appendChild(chip);
  });
}

async function saveUser(){
  const role=document.getElementById('uRole').value;
  const alias=document.getElementById('uAlias').value.trim();
  const body={role,alias_name:alias||null};

  const res=await fetch('/api/users/'+encodeURIComponent(editingUid),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await res.json();
  if(!res.ok){alert(d.error);return;}

  if(role==='vendor'||role==='customer'){
    const relation=role==='vendor'?'vendor':'customer';
    const selChips=[...document.querySelectorAll('#ubGrid .chip.on')];
    const selPids=new Set(selChips.map(c=>c.dataset.pid));
    const allChips=[...document.querySelectorAll('#ubGrid .chip')];
    const allPids=allChips.map(c=>c.dataset.pid);
    for(const pid of allPids){
      const curMembers=await fetch('/api/projects/'+encodeURIComponent(pid)+'/users').then(r=>r.json()).catch(()=>[]);
      let newMembers=curMembers.filter(m=>m.line_id!==editingUid);
      if(selPids.has(pid)) newMembers.push({line_id:editingUid,relation});
      await fetch('/api/projects/'+encodeURIComponent(pid)+'/users',{
        method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({members:newMembers.map(m=>({line_id:m.line_id,relation:m.relation}))})
      });
    }
  }

  document.getElementById('udlg').close();
  loadUsers();
}

/* ── Projects ── */

async function loadProjects(){
  const st=document.getElementById('projStatusFilter').value;
  const url='/api/projects'+(st?'?status='+encodeURIComponent(st):'');
  allProjects=await fetch(url).then(r=>r.json()).catch(()=>[]);
  renderProjects(allProjects);
}

function renderProjects(projects){
  const tb=document.getElementById('ptb');
  if(!projects.length){tb.textContent='';const tr=tb.insertRow();const td=tr.insertCell();td.colSpan=7;td.className='empty';td.textContent='無資料';return;}
  tb.textContent='';
  projects.forEach(p=>{
    const tr=tb.insertRow();tr.className='proj-row';
    tr.insertCell().textContent=p.case_number||'—';
    tr.insertCell().textContent=p.name||'—';
    tr.insertCell().textContent=p.board_name||'—';
    const tdNas=tr.insertCell();tdNas.style.cssText='font-size:11px;color:#aaa;max-width:180px;overflow:hidden;text-overflow:ellipsis';tdNas.title=p.nas_path||'';tdNas.textContent=p.nas_path?p.nas_path.split('/').pop():'—';
    const tdSt=tr.insertCell();
    const sb=document.createElement('span');sb.className='badge '+(STATUS_CLS[p.status]||'bv');sb.textContent=STATUS_LABEL[p.status]||p.status;tdSt.appendChild(sb);
    tr.insertCell().textContent=p.member_count||0;
    const tdAct=tr.insertCell();
    const eb=document.createElement('button');eb.className='btn btn-b';eb.textContent='編輯';eb.onclick=()=>openEditProject(p);tdAct.appendChild(eb);
    const mb=document.createElement('button');mb.className='btn btn-b';mb.style.marginLeft='4px';mb.textContent='人員';mb.onclick=()=>openMembers(p);tdAct.appendChild(mb);
  });
}

async function openAddProject(){
  if(!boards.length) boards=await fetch('/api/boards').then(r=>r.json()).catch(()=>[]);
  editingPid=null; importMode=false;
  document.getElementById('pdlgT').textContent='新增專案';
  document.getElementById('pName').value='';
  document.getElementById('pFolder').value='';
  document.getElementById('pFolder').placeholder='115-001-XX公館';
  document.getElementById('pNotes').value='';
  document.getElementById('pFolderField').style.display='';
  document.getElementById('pFolder').style.display='';
  document.getElementById('pFolderSelectWrap').style.display='none';
  document.getElementById('pFolderField').querySelector('.hint').textContent='將在「00. 執行中案場/」下建立';
  document.getElementById('pEditFields').style.display='none';
  _fillBoardSelect(null);
  document.getElementById('pdlg').showModal();
}

async function _loadNasFolders(selectedFull){
  if(!nasFolders.length){
    const d=await fetch('/api/nas/folders').then(r=>r.json()).catch(()=>({base:'',folders:[]}));
    nasBase=d.base||''; nasFolders=d.folders||[];
  }
  document.getElementById('pNasBase').textContent=nasBase;
  const sel=document.getElementById('pNasPath');
  while(sel.firstChild) sel.removeChild(sel.firstChild);
  const o0=document.createElement('option');o0.value='';o0.textContent='（無）';sel.appendChild(o0);
  let curName='';
  if(selectedFull && nasBase && selectedFull.indexOf(nasBase+'/')===0) curName=selectedFull.slice(nasBase.length+1);
  else if(selectedFull) curName=selectedFull;
  let matched=false;
  nasFolders.forEach(n=>{const o=document.createElement('option');o.value=n;o.textContent=n;if(n===curName){o.selected=true;matched=true;}sel.appendChild(o);});
  if(curName && !matched){
    const o=document.createElement('option');o.value='__keep__';o.textContent=curName+'（目前；非基底下）';o.selected=true;sel.appendChild(o);
    sel.dataset.keepFull=selectedFull;
  } else { delete sel.dataset.keepFull; }
}

function _fillBoardSelect(selectedId){
  const sel=document.getElementById('pBoard');
  while(sel.firstChild) sel.removeChild(sel.firstChild);
  const o0=document.createElement('option');o0.value='';o0.textContent='（不指定）';sel.appendChild(o0);
  boards.forEach(b=>{const o=document.createElement('option');o.value=b.board_id||b;o.textContent=b.board_name||b;if(selectedId&&(b.board_id||b)===selectedId)o.selected=true;sel.appendChild(o);});
}

async function openImportProject(){
  if(!boards.length) boards=await fetch('/api/boards').then(r=>r.json()).catch(()=>[]);
  editingPid=null; importMode=true;
  document.getElementById('pdlgT').textContent='匯入既有專案（不會建立 NAS 資料夾）';
  document.getElementById('pName').value='';
  document.getElementById('pNotes').value='';
  document.getElementById('pFolderField').style.display='';
  document.getElementById('pFolder').style.display='none';
  document.getElementById('pFolderSelectWrap').style.display='flex';
  document.getElementById('pFolderField').querySelector('.hint').textContent='只列出尚未綁定專案的 NAS 資料夾；選擇後該資料夾名將作為案號';
  document.getElementById('pEditFields').style.display='none';
  _fillBoardSelect(null);
  const d=await fetch('/api/nas/folders?unassigned=1').then(r=>r.json()).catch(()=>({base:'',folders:[]}));
  document.getElementById('pFolderBase').textContent=d.base||'';
  const sel=document.getElementById('pFolderSelect');
  while(sel.firstChild) sel.removeChild(sel.firstChild);
  const o0=document.createElement('option');o0.value='';o0.textContent='（無）';sel.appendChild(o0);
  (d.folders||[]).forEach(n=>{const o=document.createElement('option');o.value=n;o.textContent=n;sel.appendChild(o);});
  document.getElementById('pdlg').showModal();
}

async function openEditProject(p){
  if(!boards.length) boards=await fetch('/api/boards').then(r=>r.json()).catch(()=>[]);
  editingPid=p.project_id;
  document.getElementById('pdlgT').textContent='編輯專案';
  document.getElementById('pName').value=p.name||'';
  document.getElementById('pNotes').value=p.notes||'';
  document.getElementById('pFolderField').style.display='none';
  document.getElementById('pEditFields').style.display='';
  await _loadNasFolders(p.nas_path||'');
  document.getElementById('pNasHint').textContent='從「執行中案場」資料夾中選擇；改動不會影響 NAS 上的檔案';
  document.getElementById('pStatus').value=p.status||'active';
  const sel=document.getElementById('pBoard');
  sel.innerHTML='<option value="">（不指定）</option>';
  boards.forEach(b=>{const o=document.createElement('option');o.value=b.board_id||b;o.textContent=b.board_name||b;if((b.board_id||b)===p.trello_board_id)o.selected=true;sel.appendChild(o);});
  document.getElementById('pdlg').showModal();
}

async function saveProject(){
  const name=document.getElementById('pName').value.trim();
  if(!name){alert('請填寫專案名稱');return;}
  const board_id=document.getElementById('pBoard').value||null;
  const notes=document.getElementById('pNotes').value.trim()||null;

  let res;
  if(!editingPid){
    const folder=importMode
      ? document.getElementById('pFolderSelect').value
      : document.getElementById('pFolder').value.trim();
    if(importMode && !folder){alert('請選擇要匯入的 NAS 資料夾');return;}
    const body={name,case_number:folder,trello_board_id:board_id,notes};
    if(importMode) body.import_existing=true;
    res=await fetch('/api/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  } else {
    const status=document.getElementById('pStatus').value;
    const sel=document.getElementById('pNasPath');
    const v=sel.value;
    let nas_path=null;
    if(v==='__keep__') nas_path=sel.dataset.keepFull||null;
    else if(v) nas_path=(nasBase?nasBase+'/':'')+v;
    const body={name,trello_board_id:board_id,status,notes,nas_path};
    res=await fetch('/api/projects/'+encodeURIComponent(editingPid),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  }
  const d=await res.json();
  if(!res.ok){alert(d.error||(d.nas_warning?'NAS 警告：'+d.nas_warning:'儲存失敗'));return;}
  if(d.nas_warning) alert('注意：'+d.nas_warning);
  document.getElementById('pdlg').close();
  loadProjects();
}

async function openMembers(p){
  editingMmPid=p.project_id;
  document.getElementById('mmdlgT').textContent='專案人員：'+p.case_number+' '+p.name;
  if(!allUsers.length) allUsers=await fetch('/api/users').then(r=>r.json()).catch(()=>[]);
  projectMembers=await fetch('/api/projects/'+encodeURIComponent(p.project_id)+'/users').then(r=>r.json()).catch(()=>[]);
  populateUserSelect();
  renderMemberList();
  document.getElementById('mmdlg').showModal();
}

function populateUserSelect(){
  const sel=document.getElementById('mmUser');
  sel.innerHTML='';
  const memberIds=projectMembers.map(m=>m.line_id);
  allUsers.filter(u=>!memberIds.includes(u.line_id)).forEach(u=>{
    const o=document.createElement('option');o.value=u.line_id;o.textContent=u.display_name||(u.line_id.substring(0,8)+'…');sel.appendChild(o);
  });
}

function renderMemberList(){
  const div=document.getElementById('mmList');div.textContent='';
  if(!projectMembers.length){div.textContent='（無人員）';return;}
  projectMembers.forEach((m,i)=>{
    const chip=document.createElement('span');chip.className='member-chip';
    const relLabel={customer:'客戶',vendor:'廠商'}[m.relation]||m.relation;
    chip.textContent=(m.display_name||m.line_id.substring(0,8))+' ('+relLabel+')';
    const rm=document.createElement('span');rm.className='remove';rm.textContent='✕';
    rm.onclick=()=>{projectMembers.splice(i,1);populateUserSelect();renderMemberList();};
    chip.appendChild(rm);div.appendChild(chip);
  });
}

function addMember(){
  const sel=document.getElementById('mmUser');
  const line_id=sel.value;
  if(!line_id) return;
  const user=allUsers.find(u=>u.line_id===line_id);
  const relation=document.getElementById('mmRelation').value;
  projectMembers.push({line_id,display_name:user?user.display_name:'',relation});
  populateUserSelect();renderMemberList();
}

async function saveMembers(){
  const body={members:projectMembers.map(m=>({line_id:m.line_id,relation:m.relation}))};
  const res=await fetch('/api/projects/'+encodeURIComponent(editingMmPid)+'/users',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await res.json();
  if(!res.ok){alert(d.error);return;}
  document.getElementById('mmdlg').close();
  loadProjects();
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
    const name=b.board_name||b;
    const chip=document.createElement('span');
    chip.className='chip'+(sel.includes(name)?' on':'');
    chip.textContent=name;
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
