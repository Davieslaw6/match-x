import hashlib, hmac, secrets
from datetime import timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .config import settings
from .db import LoginFailure, Owner, UserSession, get_db, utcnow

ph = PasswordHasher()  # argon2id by default
def sha(v: str) -> str: return hashlib.sha256(v.encode()).hexdigest()

def err(status: int, code: str, msg: str):
    return HTTPException(status, {"code": code, "message": msg})

def create_owner(db: Session, username: str, password: str):
    if len(password) < 12: raise ValueError("password must be at least 12 characters")
    if db.scalar(select(func.count()).select_from(Owner)): raise ValueError("an owner already exists; use reset-owner-password")
    db.add(Owner(username=username, password_hash=ph.hash(password))); db.commit()

def reset_password(db: Session, username: str, password: str):
    if len(password) < 12: raise ValueError("password must be at least 12 characters")
    o = db.scalar(select(Owner).where(Owner.username == username))
    if not o: raise ValueError("no such owner")
    o.password_hash = ph.hash(password); db.query(UserSession).filter_by(owner_id=o.id).delete(); db.commit()

def locked(db: Session, username: str) -> bool:
    since = utcnow() - timedelta(minutes=settings.lockout_minutes)
    n = db.scalar(select(func.count()).select_from(LoginFailure).where(
        LoginFailure.username == username, LoginFailure.at > since))
    return n >= settings.max_failed_logins

def login(db: Session, username: str, password: str):
    if locked(db, username): raise err(429, "locked", "Too many failed attempts. Try again later.")
    o = db.scalar(select(Owner).where(Owner.username == username))
    try:
        if not o: ph.verify(ph.hash("x" * 12), password)  # equalise timing
        else: ph.verify(o.password_hash, password)
        if not o: raise VerifyMismatchError()
    except VerifyMismatchError:
        db.add(LoginFailure(username=username, at=utcnow())); db.commit()
        raise err(401, "invalid_credentials", "Username or password is incorrect.")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(UserSession(owner_id=o.id, token_hash=sha(token), csrf_hash=sha(csrf),
                       expires_at=utcnow() + timedelta(hours=settings.session_hours)))
    db.query(LoginFailure).filter_by(username=username).delete(); db.commit()
    return token, csrf

def current_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    tok = request.cookies.get("mx_session")
    s = db.scalar(select(UserSession).where(UserSession.token_hash == sha(tok))) if tok else None
    if not s or s.expires_at.replace(tzinfo=s.expires_at.tzinfo or __import__("datetime").timezone.utc) < utcnow():
        raise err(401, "unauthenticated", "Sign in required.")
    return s

def require_csrf(request: Request, s: UserSession = Depends(current_session)) -> UserSession:
    cookie, header = request.cookies.get("mx_csrf", ""), request.headers.get("x-csrf-token", "")
    if not cookie or not hmac.compare_digest(cookie, header) or not hmac.compare_digest(sha(cookie), s.csrf_hash):
        raise err(403, "csrf", "Missing or invalid CSRF token.")
    return s
