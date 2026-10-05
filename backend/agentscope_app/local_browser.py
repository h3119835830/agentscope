"""One-time local launch tickets; the browser never receives the admin token."""
import hashlib
import secrets
import time
from ipaddress import ip_address
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from . import db
from .config import LOCAL_BROWSER_LOGIN

COOKIE = "agentscopeLocalSession"
SESSION_SECONDS = 8 * 3600
SCHEMA = """
CREATE TABLE IF NOT EXISTS local_browser_access (
 hash TEXT PRIMARY KEY, kind TEXT NOT NULL,
 expires_at REAL NOT NULL, used_at REAL
);
"""
router = APIRouter()


def digest(value): return hashlib.sha256(value.encode()).hexdigest()


def local(request):
    if not LOCAL_BROWSER_LOGIN or not request.client: return False
    try:
        if not ip_address(request.client.host).is_loopback: return False
    except ValueError: return False
    if request.url.hostname not in ("localhost", "127.0.0.1", "::1"): return False
    origin = request.headers.get("origin")
    if origin:
        url = urlsplit(origin)
        if url.scheme != request.url.scheme or url.netloc != request.url.netloc: return False
    return request.headers.get("sec-fetch-site") not in ("cross-site", "same-site")


def authorized(request):
    if not local(request): return False
    if request.method not in ("GET", "HEAD") and not request.headers.get("origin"): return False
    value = request.cookies.get(COOKIE, "")
    if not value: return False
    with db.connect() as con:
        return bool(con.execute("SELECT 1 FROM local_browser_access WHERE hash=? AND kind='session' AND used_at IS NULL AND expires_at>?",
                                (digest(value), time.time())).fetchone())


class Redeem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str = Field(min_length=32, max_length=120)


@router.post("/api/auth/local-browser-ticket")
def mint(request: Request):
    # Middleware permits only the administrator bearer credential on this route.
    if not local(request): raise HTTPException(403, "仅支持本机启动器")
    ticket = secrets.token_urlsafe(36)
    with db.connect() as con:
        con.execute("DELETE FROM local_browser_access WHERE expires_at<?", (time.time(),))
        con.execute("INSERT INTO local_browser_access VALUES(?,?,?,NULL)", (digest(ticket), "ticket", time.time()+300))
        db.audit(con, None, "local_browser_ticket_created", "local_launcher", {})
    return {"ticket": ticket, "expires_in": 300}


@router.post("/api/auth/local-browser-redeem")
def redeem(body: Redeem, request: Request):
    if not local(request): raise HTTPException(403, "仅支持同源本机浏览器")
    session = secrets.token_urlsafe(36)
    with db.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        changed = con.execute("UPDATE local_browser_access SET used_at=? WHERE hash=? AND kind='ticket' AND used_at IS NULL AND expires_at>?",
                              (time.time(), digest(body.ticket), time.time())).rowcount
        if not changed: raise HTTPException(401, "启动链接已使用或过期，请通过本机启动器重新打开")
        con.execute("INSERT INTO local_browser_access VALUES(?,?,?,NULL)", (digest(session), "session", time.time()+SESSION_SECONDS))
        db.audit(con, None, "local_browser_connected", "local_operator", {})
    response = JSONResponse({"ok": True})
    response.set_cookie(COOKIE, session, httponly=True, samesite="strict", path="/api", max_age=SESSION_SECONDS)
    return response


@router.post("/api/auth/local-browser-close")
def close(request: Request):
    value = request.cookies.get(COOKIE, "")
    with db.connect() as con:
        con.execute("UPDATE local_browser_access SET used_at=? WHERE hash=? AND kind='session'", (time.time(), digest(value)))
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE, path="/api", httponly=True, samesite="strict")
    return response
