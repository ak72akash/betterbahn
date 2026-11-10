"""Optionaler Passwortschutz (APP_PASSWORD): einfaches Login mit signiertem Session-Cookie."""
from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from starlette.responses import JSONResponse

from app.api.zustand import Zustand, zustand
from app.config import Konfig

COOKIE = "sd_session"
OFFEN = ("/api/login", "/api/logout", "/api/auth/status", "/api/health", "/api/docs", "/api/openapi.json")
router = APIRouter(tags=["Anmeldung"])
_versuche: dict[str, list[float]] = {}


def token(cfg: Konfig) -> str:
    geheim = (cfg.session_secret or "spassdepot") + cfg.app_password
    return hmac.new(geheim.encode(), b"spassdepot-session-v1", hashlib.sha256).hexdigest()


def angemeldet(cfg: Konfig, cookies) -> bool:
    if not cfg.app_password:
        return True
    return hmac.compare_digest(cookies.get(COOKIE, ""), token(cfg))


async def auth_middleware(request: Request, call_next):
    cfg: Konfig = request.app.state.z.cfg
    pfad = request.url.path
    if (cfg.app_password and pfad.startswith("/api") and pfad not in OFFEN
            and request.method != "OPTIONS" and not angemeldet(cfg, request.cookies)):
        return JSONResponse({"detail": "Nicht angemeldet."}, status_code=401)
    return await call_next(request)


class Login(BaseModel):
    passwort: str


class AuthStatus(BaseModel):
    passwort_noetig: bool
    angemeldet: bool


@router.get("/auth/status", response_model=AuthStatus)
def status(request: Request, z: Zustand = Depends(zustand)):
    return AuthStatus(passwort_noetig=bool(z.cfg.app_password), angemeldet=angemeldet(z.cfg, request.cookies))


@router.post("/login", response_model=AuthStatus)
def login(daten: Login, request: Request, response: Response, z: Zustand = Depends(zustand)):
    ip = request.client.host if request.client else "?"
    jetzt = time.monotonic()
    letzte = [t for t in _versuche.get(ip, []) if jetzt - t < 60]
    if len(letzte) >= 5:
        raise HTTPException(429, "Zu viele Versuche. Bitte eine Minute warten.")
    if not z.cfg.app_password:
        return AuthStatus(passwort_noetig=False, angemeldet=True)
    if not hmac.compare_digest(daten.passwort.encode(), z.cfg.app_password.encode()):
        _versuche[ip] = letzte + [jetzt]
        raise HTTPException(401, "Falsches Passwort.")
    response.set_cookie(COOKIE, token(z.cfg), httponly=True, samesite="lax", secure=z.cfg.cookie_secure,
                        max_age=60 * 60 * 24 * 30, path="/")
    return AuthStatus(passwort_noetig=True, angemeldet=True)


@router.post("/logout", response_model=AuthStatus)
def logout(response: Response, z: Zustand = Depends(zustand)):
    response.delete_cookie(COOKIE, path="/")
    return AuthStatus(passwort_noetig=bool(z.cfg.app_password), angemeldet=not z.cfg.app_password)
