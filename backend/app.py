"""FastAPI app: auth, multitenant data entry, and form generation."""
from __future__ import annotations
import os
import secrets
import uuid
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import security, storage
from .generator import OUTPUT, generate
from .models import TitleJob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(ROOT, "frontend")
COUNTIES_PATH = os.path.join(ROOT, "ohio_counties.csv")

COOKIE = "ta_session"
ADMIN_COOKIE = "ta_admin"
SECURE_COOKIES = os.environ.get("TITLEAPP_SECURE_COOKIES", "").lower() in ("1", "true", "yes")

app = FastAPI(title="ODOT Title Forms")


@app.on_event("startup")
def _startup() -> None:
    storage.init_db()
    _bootstrap_admin()


def _bootstrap_admin() -> None:
    """One-time platform-admin bootstrap for hosts without CLI access.

    If no admin exists yet and BOOTSTRAP_ADMIN_EMAIL/PASSWORD are set, create one.
    Never overrides an existing admin, so it's safe to leave the vars in place
    (though removing the password var after first login is recommended).
    """
    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip()
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    name = os.environ.get("BOOTSTRAP_ADMIN_NAME", "Administrator").strip() or "Administrator"
    if not email or not password:
        return
    if storage.list_admins() or storage.get_admin_by_email(email):
        return
    storage.create_admin(email, name, security.hash_password(password))
    print(f"[bootstrap] created initial platform admin: {email}")


# --------------------------------------------------------------------- auth
def current_context(request: Request) -> Optional[dict]:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    sess = storage.get_session(token)
    if not sess:
        return None
    user = storage.get_user(sess["user_id"])
    if not user:
        return None
    biz = storage.get_business(user["business_id"])
    if not biz or not biz["active"]:
        return None
    return {"token": token, "user": user, "business": biz}


def require(request: Request) -> dict:
    ctx = current_context(request)
    if not ctx:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return ctx


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/login")
def api_login(body: LoginRequest, response: Response):
    user = storage.get_user_by_email(body.email)
    if not user or not security.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    biz = storage.get_business(user["business_id"])
    if not biz or not biz["active"]:
        raise HTTPException(403, "This account is inactive — please contact support.")
    token = security.new_session_token()
    storage.create_session(user["id"], token)
    response.set_cookie(
        COOKIE, token, httponly=True, samesite="lax", secure=SECURE_COOKIES,
        max_age=storage.SESSION_DAYS * 86400, path="/",
    )
    return {"ok": True, "user": {"name": user["name"], "email": user["email"]},
            "business": {"name": biz["name"]}}


@app.post("/api/logout")
def api_logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        storage.delete_session(token)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


def require_ready(request: Request) -> dict:
    """Authenticated AND has completed a required password change."""
    ctx = require(request)
    if ctx["user"]["must_change_password"]:
        raise HTTPException(status_code=403, detail="Password change required")
    return ctx


@app.get("/api/me")
def api_me(ctx: dict = Depends(require)):
    return {"user": {"name": ctx["user"]["name"], "email": ctx["user"]["email"]},
            "business": {"name": ctx["business"]["name"]},
            "must_change_password": bool(ctx["user"]["must_change_password"])}


class ChangePassword(BaseModel):
    new_password: str


@app.post("/api/change-password")
def api_change_password(body: ChangePassword, ctx: dict = Depends(require)):
    pw = body.new_password or ""
    if len(pw) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    storage.set_user_password(ctx["user"]["id"], security.hash_password(pw), must_change=False)
    return {"ok": True}


# --------------------------------------------------------------- admin auth
# Entirely separate from business-user auth: its own table and its own cookie.
def current_admin(request: Request) -> Optional[dict]:
    token = request.cookies.get(ADMIN_COOKIE)
    if not token:
        return None
    sess = storage.get_admin_session(token)
    if not sess:
        return None
    return storage.get_admin(sess["admin_id"])


def require_admin(request: Request) -> dict:
    admin = current_admin(request)
    if not admin:
        raise HTTPException(status_code=401, detail="Admin authentication required")
    return admin


@app.post("/api/admin/login")
def api_admin_login(body: LoginRequest, response: Response):
    admin = storage.get_admin_by_email(body.email)
    if not admin or not security.verify_password(body.password, admin["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    token = security.new_session_token()
    storage.create_admin_session(admin["id"], token)
    response.set_cookie(
        ADMIN_COOKIE, token, httponly=True, samesite="lax", secure=SECURE_COOKIES,
        max_age=storage.SESSION_DAYS * 86400, path="/",
    )
    return {"ok": True, "admin": {"name": admin["name"], "email": admin["email"]}}


@app.post("/api/admin/logout")
def api_admin_logout(request: Request, response: Response):
    token = request.cookies.get(ADMIN_COOKIE)
    if token:
        storage.delete_admin_session(token)
    response.delete_cookie(ADMIN_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/admin/me")
def api_admin_me(admin: dict = Depends(require_admin)):
    return {"admin": {"name": admin["name"], "email": admin["email"]}}


# --------------------------------------------------- admin: manage tenants
class NewBusiness(BaseModel):
    name: str


class ActiveFlag(BaseModel):
    active: bool


class NewUser(BaseModel):
    business_id: int
    email: str
    name: str
    password: Optional[str] = None


class NewPassword(BaseModel):
    password: Optional[str] = None


def _gen_password() -> str:
    return secrets.token_urlsafe(9)


@app.get("/api/admin/businesses")
def api_admin_businesses(admin: dict = Depends(require_admin)):
    out = []
    for b in storage.list_businesses():
        out.append({**b, "user_count": len(storage.list_users(b["id"]))})
    return out


@app.post("/api/admin/businesses")
def api_admin_create_business(body: NewBusiness, admin: dict = Depends(require_admin)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Business name is required")
    return {"id": storage.create_business(name), "name": name}


@app.post("/api/admin/businesses/{business_id}/active")
def api_admin_set_active(business_id: int, body: ActiveFlag, admin: dict = Depends(require_admin)):
    if not storage.get_business(business_id):
        raise HTTPException(404, "Business not found")
    storage.set_business_active(business_id, body.active)
    return {"ok": True, "active": body.active}


@app.get("/api/admin/businesses/{business_id}/users")
def api_admin_list_users(business_id: int, admin: dict = Depends(require_admin)):
    return [{"id": u["id"], "name": u["name"], "email": u["email"]}
            for u in storage.list_users(business_id)]


@app.post("/api/admin/users")
def api_admin_create_user(body: NewUser, admin: dict = Depends(require_admin)):
    if not storage.get_business(body.business_id):
        raise HTTPException(404, "Business not found")
    if storage.get_user_by_email(body.email):
        raise HTTPException(409, "A user with that email already exists")
    if not body.email.strip() or not body.name.strip():
        raise HTTPException(400, "Email and name are required")
    password = body.password or _gen_password()
    uid = storage.create_user(body.business_id, body.email, body.name, security.hash_password(password))
    return {"id": uid, "email": body.email, "name": body.name, "password": password}


@app.post("/api/admin/users/{user_id}/reset-password")
def api_admin_reset_password(user_id: int, body: NewPassword, admin: dict = Depends(require_admin)):
    user = storage.get_user(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    password = body.password or _gen_password()
    storage.set_user_password(user_id, security.hash_password(password))
    return {"ok": True, "password": password}


# --------------------------------------------------------------- generation
class GenerateRequest(BaseModel):
    job_id: Optional[str] = None
    label: Optional[str] = None
    job: TitleJob


def _job_label(job: TitleJob) -> str:
    bits = [b for b in [
        job.parcel and f"Parcel {job.parcel}{('-' + job.suffix) if job.suffix else ''}",
        job.crs, job.county,
    ] if b]
    return " · ".join(bits) or "Untitled job"


@app.post("/api/generate")
def api_generate(req: GenerateRequest, ctx: dict = Depends(require_ready)):
    business_id = ctx["business"]["id"]
    job = req.job
    # Reuse only an id that already belongs to this business.
    job_id = req.job_id
    if job_id and not storage.get_job(job_id, business_id):
        job_id = None
    job_id = job_id or f"b{business_id}-{_slug(job.parcel, job.suffix)}-{uuid.uuid4().hex[:6]}"
    label = req.label or _job_label(job)

    files = generate(job, job_id, want_pdf=False)
    storage.save_job(job_id, business_id, label, job.model_dump())

    def url(path: Optional[str]) -> Optional[str]:
        return f"/api/download/{job_id}/{os.path.basename(path)}" if path else None

    return {
        "job_id": job_id,
        "label": label,
        "files": {"re46_docx": url(files["re46_docx"]), "chain_docx": url(files["chain_docx"])},
    }


@app.get("/api/download/{job_id}/{filename}")
def api_download(job_id: str, filename: str, ctx: dict = Depends(require_ready)):
    if not storage.get_job(job_id, ctx["business"]["id"]):
        raise HTTPException(404, "File not found")  # not this business's job
    safe = os.path.basename(filename)
    path = os.path.join(OUTPUT, job_id, safe)
    if not os.path.exists(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=safe)


@app.get("/api/counties")
def api_counties(ctx: dict = Depends(require_ready)):
    counties: list[str] = []
    if os.path.exists(COUNTIES_PATH):
        with open(COUNTIES_PATH, encoding="utf-8-sig") as f:
            for i, line in enumerate(f):
                name = line.strip().strip(",")
                if not name or (i == 0 and name.lower() == "county"):
                    continue
                counties.append(name)
    return counties


@app.get("/api/jobs")
def api_list_jobs(ctx: dict = Depends(require_ready)):
    return storage.list_jobs(ctx["business"]["id"])


@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: str, ctx: dict = Depends(require_ready)):
    job = storage.get_job(job_id, ctx["business"]["id"])
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.delete("/api/jobs/{job_id}")
def api_delete_job(job_id: str, ctx: dict = Depends(require_ready)):
    storage.delete_job(job_id, ctx["business"]["id"])
    return {"ok": True}


# -------------------------------------------------------------------- pages
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    page = "index.html" if current_context(request) else "login.html"
    with open(os.path.join(FRONTEND, page), encoding="utf-8") as f:
        return f.read()


@app.get("/login", response_class=HTMLResponse)
def login_page():
    with open(os.path.join(FRONTEND, "login.html"), encoding="utf-8") as f:
        return f.read()


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page():
    with open(os.path.join(FRONTEND, "admin_login.html"), encoding="utf-8") as f:
        return f.read()


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    page = "admin.html" if current_admin(request) else "admin_login.html"
    with open(os.path.join(FRONTEND, page), encoding="utf-8") as f:
        return f.read()


def _slug(parcel: str, suffix: str) -> str:
    raw = "-".join(p for p in [parcel, suffix] if p) or "job"
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in raw)


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
