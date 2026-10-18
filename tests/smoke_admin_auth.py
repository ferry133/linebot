"""smoke: 驗證 admin UI 的 Auth0 登入閘門（spec admin-auth）。

真的載入 agents/admin_server（不 stub 模組本身），只把外部副作用換掉：
DB 由 shared.db 無 pool 時自動略過；Auth0 token 交換以 monkeypatch
authorize_access_token 取代，驗的是 callback 的 allowlist / email_verified 判斷。

跑法：python3 tests/smoke_admin_auth.py（需已安裝 flask / authlib / psycopg2-binary / pillow）
"""
import os, sys, importlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("DATABASE_URL", None)
os.environ["AUTH0_DOMAIN"] = "example.auth0.com"
os.environ["AUTH0_CLIENT_ID"] = "cid"
os.environ["AUTH0_CLIENT_SECRET"] = "csecret"

FAILS = []
def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

def load(allowed, secret="test-secret"):
    for m in [m for m in list(sys.modules) if m.startswith("agents.admin_server")]:
        del sys.modules[m]
    os.environ["ADMIN_ALLOWED_EMAILS"] = allowed
    if secret is None:
        os.environ.pop("ADMIN_SESSION_SECRET", None)
    else:
        os.environ["ADMIN_SESSION_SECRET"] = secret
    return importlib.import_module("agents.admin_server")

# SESSION_COOKIE_SECURE=True：所有請求與 session_transaction 都走同一個 https host
BASE = "https://linebot-admin.example"

def client(mod, email=None):
    c = mod.app.test_client()
    c.environ_base["wsgi.url_scheme"] = "https"
    c.environ_base["HTTP_HOST"] = "linebot-admin.example"
    if email:
        with c.session_transaction(base_url=BASE) as s:
            s["email"] = email
    return c

def do_callback(mod, userinfo):
    mod.oauth.auth0.authorize_access_token = lambda **kw: {"userinfo": userinfo}
    c = client(mod)
    r = c.get("/callback", base_url=BASE)
    with c.session_transaction(base_url=BASE) as s:
        return r, s.get("email")

ALLOW = "jiahdadm@gmail.com, Ferry133@gmail.com"

# ── 缺 session secret → 啟動失敗 ──
try:
    load(ALLOW, secret=None)
    check("missing ADMIN_SESSION_SECRET refuses to start", False, "imported fine")
except RuntimeError:
    check("missing ADMIN_SESSION_SECRET refuses to start", True)

m = load(ALLOW)

# ── 未登入 ──
c = client(m)
r = c.get("/", base_url=BASE)
check("unauth / → 302 /login", r.status_code == 302 and "/login" in r.headers["Location"], r.status_code)
r = c.get("/api/users", base_url=BASE)
check("unauth /api/users → 401", r.status_code == 401, r.status_code)
r = c.get("/api/users", base_url=BASE, headers={"Authorization": "Basic YWRtaW46Y2hhbmdlbWU="})
check("Basic Auth no longer accepted → 401", r.status_code == 401, r.status_code)
r = c.get("/health", base_url=BASE)
check("/health open → 200", r.status_code == 200, r.status_code)
r = c.put("/api/users/U123", base_url=BASE, json={"role": "admin"})
check("unauth assign admin → 401", r.status_code == 401, r.status_code)

# ── 已登入（allowlist 內，大小寫不敏感）──
c = client(m, "ferry133@gmail.com")
r = c.get("/", base_url=BASE)
check("allowed session / → 200", r.status_code == 200, r.status_code)
check("page shows login email + logout", b"ferry133@gmail.com" in r.data and b"/logout" in r.data)

# ── 移出名單後既有 session 失效 ──
m2 = load("jiahdadm@gmail.com")
c = client(m2, "ferry133@gmail.com")
check("removed from allowlist → 401", c.get("/api/boards", base_url=BASE).status_code == 401)

# ── callback 判斷 ──
m = load(ALLOW)
r, e = do_callback(m, {"email": "jiahdadm@gmail.com", "email_verified": True})
check("callback allowed+verified → 302 & session", r.status_code == 302 and e == "jiahdadm@gmail.com", (r.status_code, e))
r, e = do_callback(m, {"email": "intruder@gmail.com", "email_verified": True})
check("callback non-allowlisted → 403", r.status_code == 403 and e is None, (r.status_code, e))
r, e = do_callback(m, {"email": "jiahdadm@gmail.com", "email_verified": False})
check("callback unverified → 403", r.status_code == 403 and e is None, (r.status_code, e))
r, e = do_callback(m, {"email": "jiahdadm@gmail.com"})
check("callback missing email_verified → 403", r.status_code == 403 and e is None, (r.status_code, e))

m = load("")
r, e = do_callback(m, {"email": "jiahdadm@gmail.com", "email_verified": True})
check("empty allowlist fails closed → 403", r.status_code == 403 and e is None, (r.status_code, e))

# ── open redirect ──
m = load(ALLOW)
check("_safe_next rejects //evil", m._safe_next("//evil.com") == "/")
check("_safe_next rejects absolute", m._safe_next("https://evil.com") == "/")
check("_safe_next keeps local", m._safe_next("/?tab=projects") == "/?tab=projects")

# ── logout ──
c = client(m, "jiahdadm@gmail.com")
r = c.get("/logout", base_url=BASE)
check("logout → Auth0 /v2/logout", r.status_code == 302 and "example.auth0.com/v2/logout" in r.headers["Location"])
with c.session_transaction(base_url=BASE) as s:
    check("logout clears session", "email" not in s)

print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAIL: {FAILS}")
sys.exit(1 if FAILS else 0)
