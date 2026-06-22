#!/usr/bin/env python3
"""
Admin Web UI — 用戶 / 專案 / 工地權限管理

GET  /                      HTML 管理介面
GET  /api/boards            Trello 看板清單（from DB）
GET  /api/users             LINE 用戶列表（支援 ?role= 篩選）
PUT  /api/users/<line_id>   更新角色與專案
"""

import os
import shutil
import functools
import logging
import datetime

from flask import Flask, request, jsonify, Response
from shared.log import setup as _setup_log
from shared.db import db_exec, run_migrations
from shared.exif_gps import extract_gps as _exif_extract_gps

_setup_log()
log = logging.getLogger(__name__)

run_migrations()

app = Flask(__name__)

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "changeme")

NAS_MOUNT_PATH = os.environ.get("NAS_MOUNT_PATH", "/mnt/nas/jia.homedesign")
NAS_ACTIVE_PATH = os.path.join(NAS_MOUNT_PATH, "00. 執行中案場")
NAS_ARCHIVED_PATH = os.path.join(NAS_MOUNT_PATH, "archived")
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


# ── API routes ────────────────────────────────────────────────────────────────

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

PROJECT_TYPES = ("設計", "結構基礎", "室內裝修", "軟裝")


def _photo_folder(owner: str | None, site: str | None) -> str | None:
    """Derive the synology-photo-tagger folder slug from structured fields."""
    if owner and site:
        return f"{owner}-{site}"
    return None


def _compose_name(owner: str | None, site: str | None, ptype: str | None) -> str | None:
    """Return `{owner}-{site}-{type}` when all three present, else None."""
    if owner and site and ptype:
        return f"{owner}-{site}-{ptype}"
    return None


def _validate_project_type(ptype):
    """Return (cleaned, error_response_or_None)."""
    if ptype is None or ptype == "":
        return None, None
    if ptype not in PROJECT_TYPES:
        return None, (
            jsonify({"error": f"project_type 必須是 {' / '.join(PROJECT_TYPES)} 之一"}),
            400,
        )
    return ptype, None


def _coerce_optional_float(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return _BAD


def _coerce_optional_int(v):
    if v in (None, ""):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return _BAD


_BAD = object()  # sentinel for "value present but un-coercible"


def _validate_gps(body) -> tuple[dict, tuple | None]:
    """Parse + validate gps_lat / gps_lng / gps_radius_m from a request body.

    Returns (cleaned_dict, error_response_or_None).

    Rules:
    - All three fields are optional.
    - lat & lng must both be present-or-both-absent.
    - radius_m defaults to 50 when lat/lng present and radius missing.
    - Ranges: lat -90..90, lng -180..180, radius 1..5000.
    """
    lat = _coerce_optional_float(body.get("gps_lat"))
    lng = _coerce_optional_float(body.get("gps_lng"))
    radius = _coerce_optional_int(body.get("gps_radius_m"))

    if _BAD in (lat, lng, radius):
        return {}, (jsonify({"error": "gps_lat / gps_lng / gps_radius_m 必須為數字"}), 400)

    if (lat is None) != (lng is None):
        return {}, (jsonify({"error": "gps_lat 與 gps_lng 必須同時提供或同時省略"}), 400)

    if lat is not None:
        if not (-90.0 <= lat <= 90.0):
            return {}, (jsonify({"error": "gps_lat 須在 -90 ~ 90 之間"}), 400)
        if not (-180.0 <= lng <= 180.0):
            return {}, (jsonify({"error": "gps_lng 須在 -180 ~ 180 之間"}), 400)
        if radius is None:
            radius = 50
        if not (1 <= radius <= 5000):
            return {}, (jsonify({"error": "gps_radius_m 須在 1 ~ 5000 之間"}), 400)
    else:
        # lat/lng both absent — radius is meaningless; ignore.
        radius = None

    return {"gps_lat": lat, "gps_lng": lng, "gps_radius_m": radius}, None


SITE_LEVEL_FIELDS = ("gps_lat", "gps_lng", "gps_radius_m", "nas_path")


def _upsert_site(cur, owner_name, site_name, fields):
    """Find or create a sites row keyed by (owner_name, site_name) and apply
    any caller-provided site-level fields.

    `fields` is a dict of {column_name: value} containing only the columns
    the caller explicitly wants written. `None` in a value clears that
    column; columns not in the dict are left untouched. This lets PUT
    selectively clear GPS while not requiring every caller to think about
    every field.

    Both owner_name and site_name are required and must be non-empty.
    Returns the sites.id.
    """
    cur.execute(
        "INSERT INTO sites (owner_name, site_name) VALUES (%s, %s) "
        "ON CONFLICT (owner_name, site_name) DO NOTHING",
        (owner_name, site_name),
    )
    cur.execute(
        "SELECT id FROM sites WHERE owner_name = %s AND site_name = %s",
        (owner_name, site_name),
    )
    site_id = cur.fetchone()[0]

    if fields:
        col_names = [k for k in fields if k in SITE_LEVEL_FIELDS]
        if col_names:
            set_parts = [f"{k} = %s" for k in col_names]
            set_parts.append("updated_at = now()")
            params = [fields[k] for k in col_names] + [site_id]
            cur.execute(
                "UPDATE sites SET " + ", ".join(set_parts) + " WHERE id = %s",
                params,
            )
    return site_id


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


def _archive_nas_folder(current_path: str) -> tuple:
    """Move folder from current location into NAS_ARCHIVED_PATH. Returns (new_path, error)."""
    if not current_path or not os.path.isdir(current_path):
        return None, f"NAS 路徑不存在：{current_path}"
    try:
        os.makedirs(NAS_ARCHIVED_PATH, exist_ok=True)
    except OSError as e:
        return None, f"無法建立 archived 目錄：{e}"
    base = os.path.basename(current_path.rstrip("/"))
    dest = os.path.join(NAS_ARCHIVED_PATH, base)
    if os.path.exists(dest):
        dest = os.path.join(NAS_ARCHIVED_PATH, f"{base}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}")
    try:
        os.rename(current_path, dest)
    except OSError as e:
        return None, f"移動失敗：{e}"
    log.info("[admin] archived NAS folder: %s → %s", current_path, dest)
    return dest, None


def _restore_nas_folder(current_path: str) -> tuple:
    """Move folder from archived back to NAS_ACTIVE_PATH. Returns (new_path, error)."""
    if not current_path or not os.path.isdir(current_path):
        return None, f"NAS 路徑不存在：{current_path}"
    base = os.path.basename(current_path.rstrip("/"))
    dest = os.path.join(NAS_ACTIVE_PATH, base)
    if os.path.exists(dest):
        return None, f"目標已存在，無法還原：{dest}"
    try:
        os.rename(current_path, dest)
    except OSError as e:
        return None, f"還原失敗：{e}"
    log.info("[admin] restored NAS folder: %s → %s", current_path, dest)
    return dest, None


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
                "tb.board_name, "
                "COALESCE(s.nas_path,     p.nas_path)     AS nas_path, "
                "p.status, p.notes, p.started_at, "
                "p.completed_at, p.created_at, p.updated_at, "
                "p.owner_name, p.site_name, p.project_type, "
                "COALESCE(s.gps_lat,      p.gps_lat)      AS gps_lat, "
                "COALESCE(s.gps_lng,      p.gps_lng)      AS gps_lng, "
                "COALESCE(s.gps_radius_m, p.gps_radius_m) AS gps_radius_m, "
                "p.site_id, "
                "count(lup.line_id) AS member_count "
                "FROM projects p "
                "LEFT JOIN trello_boards tb ON tb.board_id = p.trello_board_id "
                "LEFT JOIN sites s ON s.id = p.site_id "
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
            sql += " GROUP BY p.project_id, tb.board_name, s.id ORDER BY p.created_at DESC"
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
        r["photo_folder"] = _photo_folder(r.get("owner_name"), r.get("site_name"))
    return jsonify(rows)


def _active_site_type_dup(conn, site_name, project_type, exclude_id=None) -> bool:
    """True if another active project already has this (site_name, project_type).
    Backs the public_label uniqueness rule (see change project-public-label)."""
    with conn.cursor() as cur:
        sql = ("SELECT 1 FROM projects WHERE status='active' "
               "AND site_name=%s AND project_type=%s")
        params = [site_name, project_type]
        if exclude_id:
            sql += " AND project_id <> %s::uuid"
            params.append(exclude_id)
        cur.execute(sql + " LIMIT 1", params)
        return cur.fetchone() is not None


def _site_type_conflict_resp(site_name, project_type):
    return jsonify({
        "error": (f"此建案+工種已有進行中專案：{site_name}-{project_type}。"
                  f"請把建案名改成可區分（例如加棟別/戶別，如「{site_name}-A棟」）。"),
        "conflict": "site_type",
    }), 409


@app.post("/api/projects")
@require_auth
def create_project():
    body = request.get_json() or {}
    name = (body.get("name") or "").strip()
    case_number = (body.get("case_number") or "").strip()
    trello_board_id = (body.get("trello_board_id") or None)
    notes = body.get("notes")
    import_existing = bool(body.get("import_existing"))

    owner_name = (body.get("owner_name") or "").strip() or None
    site_name = (body.get("site_name") or "").strip() or None
    project_type, err = _validate_project_type(body.get("project_type"))
    if err:
        resp, code = err
        return resp, code

    gps_fields, err = _validate_gps(body)
    if err:
        resp, code = err
        return resp, code
    gps_lat = gps_fields["gps_lat"]
    gps_lng = gps_fields["gps_lng"]
    gps_radius_m = gps_fields["gps_radius_m"]

    # If all three structured fields are present, derive `name`; otherwise the
    # caller must provide `name` directly (legacy path).
    composed = _compose_name(owner_name, site_name, project_type)
    if composed:
        name = composed

    if not name:
        return jsonify({"error": "name is required (or supply owner_name + site_name + project_type)"}), 400

    # 對外標籤 (site_name, project_type) 在 active 專案中須唯一（先擋，避免白做 NAS provisioning）
    if site_name and project_type and db_exec(
            lambda conn: _active_site_type_dup(conn, site_name, project_type)):
        return _site_type_conflict_resp(site_name, project_type)

    nas_path = None
    nas_warning = None
    if import_existing:
        folder = (body.get("nas_folder") or body.get("folder") or "").strip()
        if not folder:
            return jsonify({"error": "nas_folder is required for import"}), 400
        candidate = folder if folder.startswith("/") else os.path.join(NAS_ACTIVE_PATH, folder)
        candidate = os.path.normpath(candidate)
        if not candidate.startswith(NAS_MOUNT_PATH):
            return jsonify({"error": f"路徑須位於 {NAS_MOUNT_PATH} 之下"}), 400
        if not os.path.isdir(candidate):
            return jsonify({"error": f"資料夾不存在：{candidate}"}), 400
        nas_path = candidate
        if not case_number:
            case_number = _generate_case_number(datetime.date.today().year)
    else:
        if not case_number:
            case_number = _generate_case_number(datetime.date.today().year)
        nas_path, nas_warning = _provision_nas_folder(case_number)
        if nas_warning == "folder exists":
            return jsonify({"error": "NAS folder already exists", "folder": case_number}), 409

    def _insert(conn):
        with conn.cursor() as cur:
            # Site-level fields live on the sites table when (owner, site) is
            # available. Both projects.site_id and the legacy projects.{gps_*,
            # nas_path} columns are written for one-release back-compat.
            site_id = None
            if owner_name and site_name:
                # Only propagate explicitly user-provided GPS to sites; the
                # derived nas_path stays on projects for now (see design D7).
                # A brand-new site will still get its first nas_path on the
                # first admin edit via PUT.
                site_fields = {}
                if "gps_lat" in body:
                    site_fields["gps_lat"] = gps_lat
                if "gps_lng" in body:
                    site_fields["gps_lng"] = gps_lng
                if "gps_radius_m" in body:
                    site_fields["gps_radius_m"] = gps_radius_m
                site_id = _upsert_site(cur, owner_name, site_name, site_fields)

            cur.execute(
                "INSERT INTO projects (case_number, name, trello_board_id, nas_path, notes, "
                "owner_name, site_name, project_type, "
                "gps_lat, gps_lng, gps_radius_m, site_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING project_id",
                (case_number, name, trello_board_id, nas_path, notes,
                 owner_name, site_name, project_type,
                 gps_lat, gps_lng, gps_radius_m, site_id),
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
                "tb.board_name, "
                "COALESCE(s.nas_path,     p.nas_path)     AS nas_path, "
                "p.status, p.notes, p.started_at, "
                "p.completed_at, p.created_at, p.updated_at, "
                "p.owner_name, p.site_name, p.project_type, "
                "COALESCE(s.gps_lat,      p.gps_lat)      AS gps_lat, "
                "COALESCE(s.gps_lng,      p.gps_lng)      AS gps_lng, "
                "COALESCE(s.gps_radius_m, p.gps_radius_m) AS gps_radius_m, "
                "p.site_id "
                "FROM projects p "
                "LEFT JOIN trello_boards tb ON tb.board_id = p.trello_board_id "
                "LEFT JOIN sites s ON s.id = p.site_id "
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
    r["photo_folder"] = _photo_folder(r.get("owner_name"), r.get("site_name"))
    return jsonify(r)


@app.put("/api/projects/<project_id>")
@require_auth
def update_project(project_id: str):
    body = request.get_json() or {}
    allowed = {"name", "trello_board_id", "status", "notes", "nas_path",
               "owner_name", "site_name", "project_type",
               "gps_lat", "gps_lng", "gps_radius_m"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return jsonify({"error": "no valid fields"}), 400

    if any(k in updates for k in ("gps_lat", "gps_lng", "gps_radius_m")):
        # _validate_gps treats missing keys as None — for PUT we want partial
        # updates to be additive on top of the row's current GPS, not "set the
        # missing ones to null". So fetch current values and merge before
        # validating.
        def _cur_gps(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gps_lat, gps_lng, gps_radius_m "
                    "FROM projects WHERE project_id = %s::uuid",
                    (project_id,),
                )
                return cur.fetchone()
        cur_gps = db_exec(_cur_gps)
        if cur_gps is None:
            return jsonify({"error": "not found"}), 404
        merged = {
            "gps_lat": updates.get("gps_lat", cur_gps[0]),
            "gps_lng": updates.get("gps_lng", cur_gps[1]),
            "gps_radius_m": updates.get("gps_radius_m", cur_gps[2]),
        }
        gps_clean, err = _validate_gps(merged)
        if err:
            resp, code = err
            return resp, code
        # Only overwrite the keys the caller actually sent
        for k in ("gps_lat", "gps_lng", "gps_radius_m"):
            if k in updates:
                updates[k] = gps_clean[k]

    valid_statuses = {"active", "completed", "archived"}
    if "status" in updates and updates["status"] not in valid_statuses:
        return jsonify({"error": f"invalid status: {updates['status']}"}), 400

    if "project_type" in updates:
        cleaned, err = _validate_project_type(updates["project_type"])
        if err:
            resp, code = err
            return resp, code
        updates["project_type"] = cleaned

    # Normalize blank strings → None for the structured fields
    for k in ("owner_name", "site_name"):
        if k in updates:
            v = (updates[k] or "").strip()
            updates[k] = v or None

    # Re-compose `name` when all three structured fields end up non-null.
    # We need the merged (current + update) view to decide.
    if any(k in updates for k in ("owner_name", "site_name", "project_type")):
        def _cur_structured(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT owner_name, site_name, project_type "
                    "FROM projects WHERE project_id = %s::uuid",
                    (project_id,),
                )
                return cur.fetchone()
        existing = db_exec(_cur_structured)
        if existing is None:
            return jsonify({"error": "not found"}), 404
        cur_owner, cur_site, cur_type = existing
        new_owner = updates.get("owner_name", cur_owner)
        new_site = updates.get("site_name", cur_site)
        new_type = updates.get("project_type", cur_type)
        composed = _compose_name(new_owner, new_site, new_type)
        if composed and "name" not in updates:
            updates["name"] = composed

    if "nas_path" in updates:
        new_nas = (updates["nas_path"] or "").strip() or None
        if new_nas:
            new_nas = os.path.normpath(new_nas)
            if not new_nas.startswith(NAS_MOUNT_PATH):
                return jsonify({"error": f"nas_path 必須位於 {NAS_MOUNT_PATH} 之下"}), 400
            if not os.path.isdir(new_nas):
                return jsonify({"error": f"資料夾不存在：{new_nas}"}), 400
        updates["nas_path"] = new_nas

    nas_warning = None
    if "status" in updates:
        def _cur(conn):
            with conn.cursor() as cur:
                cur.execute("SELECT status, nas_path FROM projects WHERE project_id = %s::uuid", (project_id,))
                return cur.fetchone()
        row = db_exec(_cur)
        if not row:
            return jsonify({"error": "not found"}), 404
        old_status, old_nas = row
        new_status = updates["status"]

        def _other_active_refs(path: str) -> int:
            def _q(conn):
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM projects "
                        "WHERE nas_path = %s AND status != 'archived' AND project_id != %s::uuid",
                        (path, project_id),
                    )
                    return cur.fetchone()[0]
            return db_exec(_q) or 0

        if old_status != new_status:
            if new_status == "archived" and old_nas:
                if _other_active_refs(old_nas) > 0:
                    nas_warning = "folder still in use"
                else:
                    moved, err = _archive_nas_folder(old_nas)
                    if err:
                        return jsonify({"error": err}), 500
                    updates["nas_path"] = moved
            elif old_status == "archived" and new_status == "active" and old_nas:
                # If folder physically still under active area (because other refs kept it there), just flip DB.
                if old_nas.startswith(NAS_ACTIVE_PATH) and os.path.isdir(old_nas):
                    nas_warning = "folder already in active area"
                else:
                    moved, err = _restore_nas_folder(old_nas)
                    if err:
                        return jsonify({"error": err}), 500
                    updates["nas_path"] = moved
            elif old_status == "archived" and new_status == "completed":
                return jsonify({"error": "請先還原為進行中後再標記已完成"}), 400

    # (site_name, project_type) 在 active 專案中須唯一——改名/改工種/重新啟用都可能撞。
    # 以「更新後」有效值判斷（排除自己）。
    def _eff(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT site_name, project_type, status FROM projects WHERE project_id=%s::uuid",
                (project_id,),
            )
            return cur.fetchone()
    eff = db_exec(_eff)
    if eff is None:
        return jsonify({"error": "not found"}), 404
    eff_site = updates.get("site_name", eff[0])
    eff_type = updates.get("project_type", eff[1])
    eff_status = updates.get("status", eff[2])
    if eff_status == "active" and eff_site and eff_type and db_exec(
            lambda conn: _active_site_type_dup(conn, eff_site, eff_type, exclude_id=project_id)):
        return _site_type_conflict_resp(eff_site, eff_type)

    def _upd(conn):
        with conn.cursor() as cur:
            # Read the project's current site identity so we can decide
            # whether to keep the existing sites row, switch to a different
            # one, or attach to a fresh one.
            cur.execute(
                "SELECT owner_name, site_name, site_id "
                "FROM projects WHERE project_id = %s::uuid",
                (project_id,),
            )
            row = cur.fetchone()
            if row is None:
                return 0
            cur_owner, cur_site, cur_site_id = row

            effective_owner = updates.get("owner_name", cur_owner)
            effective_site  = updates.get("site_name",  cur_site)

            # Build the dict of site-level field overrides explicitly sent
            # in this PUT (so we propagate clears too).
            site_field_overrides = {
                k: updates[k] for k in SITE_LEVEL_FIELDS if k in updates
            }

            local_updates = dict(updates)

            if effective_owner and effective_site:
                new_site_id = _upsert_site(
                    cur,
                    effective_owner,
                    effective_site,
                    site_field_overrides,
                )
                if new_site_id != cur_site_id:
                    local_updates["site_id"] = new_site_id
            # else: project is becoming or staying legacy (no site).
            # Don't touch site_id here; leave whatever was there.

            set_parts = [f"{k} = %s" for k in local_updates]
            params = list(local_updates.values())
            if local_updates.get("status") == "archived":
                set_parts.append("completed_at = now()")
            set_parts.append("updated_at = now()")
            sql = "UPDATE projects SET " + ", ".join(set_parts) + " WHERE project_id = %s::uuid"
            params.append(project_id)
            cur.execute(sql, params)
            return cur.rowcount

    rows = db_exec(_upd)
    if not rows:
        return jsonify({"error": "not found"}), 404
    resp = {"ok": True}
    if nas_warning:
        resp["nas_warning"] = nas_warning
    return jsonify(resp)


@app.post("/api/projects/extract-gps")
@require_auth
def extract_gps_endpoint():
    """Read GPS EXIF from an uploaded JPEG or HEIC and return `{lat, lng}`.

    Used by the project-management UI's "上傳 sample 相片自動萃取" button so
    the user doesn't have to type coordinates. Per consolidate-project-registry
    change: ownership of the EXIF extraction flow moved from synophoto to
    linebot.
    """
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify({"error": "請上傳檔案欄位 'file'"}), 400
    try:
        lat, lng = _exif_extract_gps(f.stream)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"lat": lat, "lng": lng})


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

/* ── 手機版（<=680px）：寬表格轉成卡片式堆疊 ── */
@media (max-width:680px){
  header{padding:12px 16px}
  header h1{font-size:16px}
  nav{padding:0 6px;overflow-x:auto;-webkit-overflow-scrolling:touch}
  nav button{padding:11px 14px;font-size:13px;white-space:nowrap}
  main{margin:14px auto;padding:0 10px}
  .card{padding:14px}
  .filter-row{gap:6px}
  .filter-row select,.filter-row input{flex:1;min-width:0}
  dialog{padding:18px;width:95vw}
  /* table → cards：thead 隱藏，每列一張卡，欄名用 data-label 當標籤 */
  table,tbody,tr,td{display:block;width:100%}
  thead{display:none}
  tr{border:1px solid #eee;border-radius:8px;margin-bottom:12px;padding:8px 12px;background:#fff}
  td{padding:5px 0!important;border:none!important;display:flex;justify-content:space-between;gap:12px;align-items:center;max-width:none!important}
  td::before{content:attr(data-label);color:#999;font-size:12px;font-weight:600;flex:0 0 84px;text-align:left}
  td[data-label="操作"]{flex-wrap:wrap;justify-content:flex-start}
  td[data-label="操作"]::before{flex-basis:100%;margin-bottom:6px}
  td.empty{display:block;text-align:center}
  td.empty::before{display:none}
  .btn+.btn{margin-left:0}
  td .btn{margin:2px 4px 2px 0}
}
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
      <thead><tr><th>名稱</th><th>Trello 看板</th><th>相片資料夾</th><th>GPS</th><th>NAS 資料夾</th><th>狀態</th><th>人員數</th><th>操作</th></tr></thead>
      <tbody id="ptb"><tr><td colspan="8" class="empty">載入中…</td></tr></tbody>
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
  <div id="pLegacyBanner" style="display:none;background:#fef3c7;border:1px solid #f59e0b;padding:8px;border-radius:4px;margin-bottom:10px;font-size:12px;color:#92400e">
    此既有專案尚未補三個結構化欄位（業主 / 案場 / 型態）。補齊後 synology-photo-tagger 才能 auto-move 相片到 <code>/photo/officephoto/&lt;業主-案場&gt;/</code>。
  </div>
  <div class="field"><label class="lbl">業主姓名</label><input type="text" id="pOwner" placeholder="例：曾宇晟" oninput="_previewProjName()"></div>
  <div class="field"><label class="lbl">案場名稱</label><input type="text" id="pSite" placeholder="例：大宅天景" oninput="_previewProjName()"></div>
  <div class="field"><label class="lbl">專案型態</label>
    <select id="pType" onchange="_previewProjName()">
      <option value="">（未指定）</option>
      <option value="設計">設計</option>
      <option value="結構基礎">結構基礎</option>
      <option value="室內裝修">室內裝修</option>
      <option value="軟裝">軟裝</option>
    </select>
  </div>
  <div id="pNamePreview" class="hint" style="margin-top:-4px;margin-bottom:8px;color:#0369a1"></div>
  <div class="field"><label class="lbl">專案名稱</label><input type="text" id="pName" placeholder="三欄位齊全會自動組合；不齊全請手填"></div>
  <div class="field" id="pFolderField"><label class="lbl">案號（即 NAS 資料夾名）</label>
    <input type="text" id="pFolder" placeholder="留空自動生成 115年第N案">
    <div id="pFolderSelectWrap" style="display:none;align-items:center;gap:6px">
      <span id="pFolderBase" style="font-size:11px;color:#888;white-space:nowrap"></span>
      <span style="color:#888">/</span>
      <select id="pFolderSelect" style="font-size:12px;flex:1"><option value="">（無）</option></select>
    </div>
    <p class="hint">案號將作為 NAS 資料夾名建立於「00. 執行中案場/」下；可自訂如 115-001-XX公館</p></div>
  <div class="field" id="pImportCaseField" style="display:none"><label class="lbl">案號（選填）</label>
    <input type="text" id="pImportCase" placeholder="留空自動生成 115年第N案">
    <p class="hint">同一資料夾可被多個專案共用，請輸入獨立案號（或留空 auto-gen）</p></div>
  <div class="field">
    <label class="lbl">Trello 看板</label>
    <select id="pBoard"><option value="">（不指定）</option></select>
  </div>
  <div class="field"><label class="lbl">備註</label><textarea id="pNotes" rows="2"></textarea></div>
  <div class="field" id="pGpsField">
    <label class="lbl">GPS 中心點與半徑 <span class="hint" style="color:#888">（用於 synophoto tagger 自動命名 / 歸檔；不填則此案不自動）</span></label>
    <div class="hint" style="font-size:11px;color:#6b7280;margin-bottom:6px">⚙️ 此欄位屬於案場（業主-案場）。同案場不同 project type 共用同一組值。</div>
    <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
      <input type="number" step="0.000001" id="pGpsLat" placeholder="緯度" style="flex:1;min-width:120px">
      <input type="number" step="0.000001" id="pGpsLng" placeholder="經度" style="flex:1;min-width:120px">
      <input type="number" id="pGpsRadius" placeholder="半徑(m)" min="1" max="5000" value="50" style="width:90px">
    </div>
    <div style="margin-top:6px;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
      <input type="file" id="pGpsPhoto" accept="image/*,.heic,.HEIC">
      <button class="btn btn-b" type="button" onclick="extractGpsFromPhoto()">從相片萃取 GPS</button>
      <span id="pGpsStatus" style="font-size:11px;color:#666"></span>
    </div>
  </div>
  <!-- Edit-only fields -->
  <div id="pEditFields" style="display:none">
    <div class="field"><label class="lbl">NAS 路徑</label>
      <div class="hint" style="font-size:11px;color:#6b7280;margin-bottom:6px">⚙️ 此欄位屬於案場（業主-案場）。同案場不同 project type 共用同一個 NAS 資料夾。</div>
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
let boards=[], editingUid=null;
let allProjects=[], editingPid=null, importMode=false, projectMembers=[], editingMmPid=null;
let nasFolders=[], nasBase='', editingOrigStatus='active';
let allUsers=[];

function switchTab(t){
  document.querySelectorAll('nav button').forEach((b,i)=>b.classList.toggle('active',['users','projects'][i]===t));
  document.querySelectorAll('.tab').forEach(el=>el.classList.remove('active'));
  const id='tab'+t.charAt(0).toUpperCase()+t.slice(1);
  document.getElementById(id).classList.add('active');
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
    const UL=['頭貼','顯示名稱','簡稱','LINE ID','角色','建立時間','操作'];
    [...tr.cells].forEach((c,i)=>c.dataset.label=UL[i]||'');
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
  if(!projects.length){tb.textContent='';const tr=tb.insertRow();const td=tr.insertCell();td.colSpan=9;td.className='empty';td.textContent='無資料';return;}
  tb.textContent='';
  projects.forEach(p=>{
    const tr=tb.insertRow();tr.className='proj-row';
    tr.insertCell().textContent=p.name||'—';
    tr.insertCell().textContent=p.board_name||'—';
    const tdPf=tr.insertCell();
    if(p.photo_folder){tdPf.textContent=p.photo_folder;tdPf.style.fontSize='12px';}
    else{tdPf.textContent='—';tdPf.style.color='#999';tdPf.style.fontSize='12px';tdPf.title='請補業主 / 案場 / 型態三欄';}
    const tdGps=tr.insertCell();tdGps.style.fontSize='11px';
    if(p.gps_lat!=null && p.gps_lng!=null){
      tdGps.textContent=Number(p.gps_lat).toFixed(4)+', '+Number(p.gps_lng).toFixed(4);
      tdGps.title='半徑 '+(p.gps_radius_m||50)+' m';
    } else {
      tdGps.textContent='—';tdGps.style.color='#999';tdGps.title='未設定 GPS — synophoto tagger 無法自動命名 / 歸檔此案';
    }
    const tdNas=tr.insertCell();tdNas.style.cssText='font-size:12px;max-width:260px;overflow:hidden;text-overflow:ellipsis';tdNas.title=p.nas_path||'';tdNas.textContent=p.nas_path?p.nas_path.split('/').pop():'—';
    const tdSt=tr.insertCell();
    const sb=document.createElement('span');sb.className='badge '+(STATUS_CLS[p.status]||'bv');sb.textContent=STATUS_LABEL[p.status]||p.status;tdSt.appendChild(sb);
    tr.insertCell().textContent=p.member_count||0;
    const tdAct=tr.insertCell();
    const archived=p.status==='archived';
    const eb=document.createElement('button');eb.className='btn btn-b';eb.textContent='編輯';eb.onclick=()=>openEditProject(p);if(archived){eb.disabled=true;eb.style.opacity='0.4';eb.style.cursor='not-allowed';}tdAct.appendChild(eb);
    const mb=document.createElement('button');mb.className='btn btn-b';mb.style.marginLeft='4px';mb.textContent='人員';mb.onclick=()=>openMembers(p);if(archived){mb.disabled=true;mb.style.opacity='0.4';mb.style.cursor='not-allowed';}tdAct.appendChild(mb);
    if(archived){
      const rb=document.createElement('button');rb.className='btn btn-g';rb.style.marginLeft='4px';rb.textContent='還原';rb.onclick=()=>restoreProject(p);tdAct.appendChild(rb);
    }
    const PL=['名稱','Trello 看板','相片資料夾','GPS','NAS 資料夾','狀態','人員數','操作'];
    [...tr.cells].forEach((c,i)=>c.dataset.label=PL[i]||'');
  });
}

function _resetStructured(){
  document.getElementById('pOwner').value='';
  document.getElementById('pSite').value='';
  document.getElementById('pType').value='';
  document.getElementById('pLegacyBanner').style.display='none';
  _previewProjName();
}

function _resetGps(){
  document.getElementById('pGpsLat').value='';
  document.getElementById('pGpsLng').value='';
  document.getElementById('pGpsRadius').value='50';
  document.getElementById('pGpsPhoto').value='';
  document.getElementById('pGpsStatus').textContent='';
}

function _gpsPayload(){
  const lat=document.getElementById('pGpsLat').value.trim();
  const lng=document.getElementById('pGpsLng').value.trim();
  const radius=document.getElementById('pGpsRadius').value.trim();
  const out={};
  if(lat!==''||lng!==''){
    out.gps_lat = lat===''?null:parseFloat(lat);
    out.gps_lng = lng===''?null:parseFloat(lng);
    out.gps_radius_m = radius===''?50:parseInt(radius,10);
  } else {
    // Explicitly clear when editing and user removed coords
    out.gps_lat = null;
    out.gps_lng = null;
    out.gps_radius_m = null;
  }
  return out;
}

async function extractGpsFromPhoto(){
  const f=document.getElementById('pGpsPhoto').files[0];
  const st=document.getElementById('pGpsStatus');
  if(!f){st.textContent='請先選擇相片檔';st.style.color='#b00';return;}
  st.textContent='萃取中…';st.style.color='#666';
  const fd=new FormData();fd.append('file',f);
  let res;
  try{ res=await fetch('/api/projects/extract-gps',{method:'POST',body:fd}); }
  catch(e){ st.textContent='連線失敗：'+e.message;st.style.color='#b00';return; }
  const d=await res.json().catch(()=>({}));
  if(!res.ok){st.textContent=d.error||'萃取失敗';st.style.color='#b00';return;}
  document.getElementById('pGpsLat').value=d.lat;
  document.getElementById('pGpsLng').value=d.lng;
  st.textContent='已自 EXIF 取得座標 ('+d.lat.toFixed(6)+', '+d.lng.toFixed(6)+')';
  st.style.color='#067a3a';
}

function _previewProjName(){
  const o=document.getElementById('pOwner').value.trim();
  const s=document.getElementById('pSite').value.trim();
  const t=document.getElementById('pType').value;
  const prev=document.getElementById('pNamePreview');
  if(o&&s&&t){
    prev.textContent='名稱會自動組合為：'+o+'-'+s+'-'+t+'　（photo_folder = '+o+'-'+s+'）';
    document.getElementById('pName').value=o+'-'+s+'-'+t;
  } else if(o||s||t){
    prev.textContent='提示：三欄位齊全才會自動組合 name 並提供 photo_folder';
  } else {
    prev.textContent='';
  }
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
  document.getElementById('pImportCaseField').style.display='none';
  document.getElementById('pFolderField').querySelector('.hint').textContent='將在「00. 執行中案場/」下建立';
  document.getElementById('pEditFields').style.display='none';
  _resetStructured();
  _resetGps();
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
  _resetStructured();
  _resetGps();
  document.getElementById('pFolderField').style.display='';
  document.getElementById('pFolder').style.display='none';
  document.getElementById('pFolderSelectWrap').style.display='flex';
  document.getElementById('pFolderField').querySelector('.hint').textContent='同一資料夾可被多個專案共用';
  document.getElementById('pImportCaseField').style.display='';
  document.getElementById('pImportCase').value='';
  document.getElementById('pEditFields').style.display='none';
  _fillBoardSelect(null);
  const d=await fetch('/api/nas/folders').then(r=>r.json()).catch(()=>({base:'',folders:[]}));
  document.getElementById('pFolderBase').textContent=d.base||'';
  const sel=document.getElementById('pFolderSelect');
  while(sel.firstChild) sel.removeChild(sel.firstChild);
  const o0=document.createElement('option');o0.value='';o0.textContent='（無）';sel.appendChild(o0);
  (d.folders||[]).forEach(n=>{const o=document.createElement('option');o.value=n;o.textContent=n;sel.appendChild(o);});
  document.getElementById('pdlg').showModal();
}

async function openEditProject(p){
  if(!boards.length) boards=await fetch('/api/boards').then(r=>r.json()).catch(()=>[]);
  editingPid=p.project_id; editingOrigStatus=p.status||'active';
  document.getElementById('pdlgT').textContent='編輯專案';
  document.getElementById('pName').value=p.name||'';
  document.getElementById('pNotes').value=p.notes||'';
  document.getElementById('pFolderField').style.display='none';
  document.getElementById('pImportCaseField').style.display='none';
  document.getElementById('pEditFields').style.display='';
  document.getElementById('pOwner').value=p.owner_name||'';
  document.getElementById('pSite').value=p.site_name||'';
  document.getElementById('pType').value=p.project_type||'';
  const allMissing=!p.owner_name && !p.site_name && !p.project_type;
  document.getElementById('pLegacyBanner').style.display=allMissing?'':'none';
  _previewProjName();
  _resetGps();
  if(p.gps_lat!=null){document.getElementById('pGpsLat').value=p.gps_lat;}
  if(p.gps_lng!=null){document.getElementById('pGpsLng').value=p.gps_lng;}
  if(p.gps_radius_m!=null){document.getElementById('pGpsRadius').value=p.gps_radius_m;}
  await _loadNasFolders(p.nas_path||'');
  document.getElementById('pNasHint').textContent='從「執行中案場」資料夾中選擇；改動不會影響 NAS 上的檔案';
  document.getElementById('pStatus').value=p.status||'active';
  const sel=document.getElementById('pBoard');
  sel.innerHTML='<option value="">（不指定）</option>';
  boards.forEach(b=>{const o=document.createElement('option');o.value=b.board_id||b;o.textContent=b.board_name||b;if((b.board_id||b)===p.trello_board_id)o.selected=true;sel.appendChild(o);});
  document.getElementById('pdlg').showModal();
}

function _structuredPayload(){
  const o=document.getElementById('pOwner').value.trim()||null;
  const s=document.getElementById('pSite').value.trim()||null;
  const t=document.getElementById('pType').value||null;
  return {owner_name:o, site_name:s, project_type:t};
}

async function saveProject(){
  const owner=document.getElementById('pOwner').value.trim();
  const site=document.getElementById('pSite').value.trim();
  const ptype=document.getElementById('pType').value;
  const allStructured=owner && site && ptype;
  const name=allStructured ? (owner+'-'+site+'-'+ptype) : document.getElementById('pName').value.trim();
  if(!name){alert('請填寫專案名稱（或補齊業主 / 案場 / 型態三欄）');return;}
  const board_id=document.getElementById('pBoard').value||null;
  const notes=document.getElementById('pNotes').value.trim()||null;
  const structured=_structuredPayload();
  const gps=_gpsPayload();

  let res;
  if(!editingPid){
    let body;
    if(importMode){
      const folder=document.getElementById('pFolderSelect').value;
      if(!folder){alert('請選擇要匯入的 NAS 資料夾');return;}
      const caseNum=document.getElementById('pImportCase').value.trim();
      body={name,nas_folder:folder,trello_board_id:board_id,notes,import_existing:true,...structured,...gps};
      if(caseNum) body.case_number=caseNum;
    } else {
      const folder=document.getElementById('pFolder').value.trim();
      body={name,case_number:folder,trello_board_id:board_id,notes,...structured,...gps};
    }
    res=await fetch('/api/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  } else {
    const status=document.getElementById('pStatus').value;
    if(status==='archived' && editingOrigStatus!=='archived'){
      if(!confirm('將「'+name+'」設為「已封存」會：\n\n・把 NAS 資料夾從「00. 執行中案場/」搬到「archived/」\n・停止所有通知推播\n・客戶無法再查詢此專案進度\n\n稍後可在列表上按「還原」回復。確定要封存嗎？')) return;
    }
    const sel=document.getElementById('pNasPath');
    const v=sel.value;
    let nas_path=null;
    if(v==='__keep__') nas_path=sel.dataset.keepFull||null;
    else if(v) nas_path=(nasBase?nasBase+'/':'')+v;
    const body={name,trello_board_id:board_id,status,notes,nas_path,...structured,...gps};
    res=await fetch('/api/projects/'+encodeURIComponent(editingPid),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  }
  const d=await res.json();
  if(!res.ok){alert(d.error||(d.nas_warning?'NAS 警告：'+d.nas_warning:'儲存失敗'));return;}
  if(d.nas_warning){
    const msg={
      'folder still in use':'資料夾仍有其他進行中專案使用，本次不搬移實體資料夾',
      'folder already in active area':'實體資料夾已在執行中案場下（其他專案保留），僅更新狀態',
      'template not found':'NAS 範本資料夾不存在，未建立資料夾',
      'folder exists':'NAS 資料夾已存在',
    }[d.nas_warning]||d.nas_warning;
    alert('注意：'+msg);
  }
  document.getElementById('pdlg').close();
  loadProjects();
}

async function restoreProject(p){
  if(!confirm('將「'+p.name+'」還原為進行中？資料夾會搬回「00. 執行中案場/」。')) return;
  const res=await fetch('/api/projects/'+encodeURIComponent(p.project_id),{
    method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({status:'active'})
  });
  const d=await res.json().catch(()=>({}));
  if(!res.ok){alert(d.error||'還原失敗');return;}
  allProjects=[]; loadProjects();
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
