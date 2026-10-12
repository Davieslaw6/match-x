import uuid
from decimal import Decimal
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from . import auth
from .config import settings
from .db import get_db, init_db
from .engine.markets import correct_score, grid, markets
from .odds import core as odds
from .tickets import core as tk

app = FastAPI(title="MATCH X", version="0.3.0")
init_db()
from .chat_api import router as chat_router
app.include_router(chat_router)
from .explorer import router as explorer_router
app.include_router(explorer_router)
from .tickets_api import router as tickets_router
app.include_router(tickets_router)
from .imports_api import router as imports_router
from .booking_api import router as booking_router
from .ops_api import router as ops_router
for _r in (imports_router, booking_router, ops_router): app.include_router(_r)
from .ratelimit import limiter
app.middleware("http")(limiter)
if settings.cors_origin:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware, allow_origins=[settings.cors_origin], allow_credentials=True, allow_methods=["GET", "POST", "PUT"], allow_headers=["content-type", "x-csrf-token", "idempotency-key"])
from fastapi.exceptions import RequestValidationError
@app.exception_handler(RequestValidationError)
async def validation(request, exc):
    return envelope(request, 422, "validation_error", "Request validation failed.", [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()])
SECURE = settings.env == "production"

@app.middleware("http")
async def mw(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = rid
    resp = await call_next(request)
    resp.headers.update({"x-request-id": rid, "x-content-type-options": "nosniff", "referrer-policy": "no-referrer",
        "x-frame-options": "DENY", "content-security-policy": "default-src 'none'; frame-ancestors 'none'"})
    return resp

def envelope(request, status, code, message, details=None):
    return JSONResponse(status_code=status, content={"code": code, "message": message, "details": details,
                        "request_id": getattr(request.state, "request_id", None)})

from starlette.exceptions import HTTPException as StarletteHTTPException
@app.exception_handler(StarletteHTTPException)
async def http_exc(request, exc):
    d = exc.detail if isinstance(exc.detail, dict) else {"code": "not_found" if exc.status_code == 404 else "error", "message": str(exc.detail)}
    return envelope(request, exc.status_code, d["code"], d["message"])

@app.exception_handler(Exception)
async def unhandled(request, exc): return envelope(request, 500, "internal_error", "Unexpected error")

@app.get("/api/v1/health/live")
def live(): return {"status": "ok"}

@app.get("/api/v1/health/ready")
def ready(db: Session = Depends(get_db)):
    try: db.execute(__import__("sqlalchemy").text("select 1")); dbs = "ok"
    except Exception: dbs = "down"
    return JSONResponse(status_code=200 if dbs == "ok" else 503,
        content={"status": "ready" if dbs == "ok" else "not_ready", "checks": {"database": dbs, "providers": "unchecked"}})

def set_cookie(resp: Response, k, v, http_only):
    resp.set_cookie(k, v, httponly=http_only, secure=SECURE, samesite="lax", path="/")

@app.get("/api/v1/auth/session")
def session(request: Request, response: Response, db: Session = Depends(get_db)):
    csrf = request.cookies.get("mx_csrf") or __import__("secrets").token_urlsafe(32)
    set_cookie(response, "mx_csrf", csrf, False)
    try: auth.current_session(request, db); signed = True
    except HTTPException: signed = False
    return {"authenticated": signed, "csrf_token": csrf}

class Login(BaseModel):
    username: str = Field(max_length=64); password: str = Field(max_length=256)

@app.post("/api/v1/auth/login")
def login(body: Login, request: Request, response: Response, db: Session = Depends(get_db)):
    cookie, header = request.cookies.get("mx_csrf", ""), request.headers.get("x-csrf-token", "")
    if not cookie or cookie != header: raise auth.err(403, "csrf", "Missing or invalid CSRF token.")
    token, csrf = auth.login(db, body.username, body.password)
    set_cookie(response, "mx_session", token, True); set_cookie(response, "mx_csrf", csrf, False)
    return {"authenticated": True, "csrf_token": csrf}

@app.post("/api/v1/auth/logout")
def logout(response: Response, s=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    db.delete(s); db.commit(); response.delete_cookie("mx_session"); return {"authenticated": False}

class Rates(BaseModel):
    home_xg: float = Field(gt=0, le=6); away_xg: float = Field(gt=0, le=6); rho: float = Field(0, ge=-0.2, le=0.2)

@app.post("/api/v1/predict/from-rates")
def from_rates(b: Rates, _=Depends(auth.require_csrf)):
    try: g = grid(b.home_xg, b.away_xg, b.rho)
    except ValueError as e: raise HTTPException(422, {"code": "invalid_rates", "message": str(e)})
    return {"kind": "calculation", "note": "Statistical estimate from supplied expected goals; not advice or a guarantee.",
            "markets": markets(g), "correct_score": correct_score(g)}

class Prices(BaseModel):
    odds: list[Decimal] = Field(min_length=2, max_length=20); method: str = "proportional"

@app.post("/api/v1/odds/devig")
def devig(b: Prices, _=Depends(auth.require_csrf)):
    fn = {"proportional": odds.devig_proportional, "power": odds.devig_power, "shin": odds.devig_shin}.get(b.method)
    if not fn: raise HTTPException(422, {"code": "bad_method", "message": "method must be proportional, power or shin"})
    try:
        return {"overround": str(odds.overround(b.odds)), "implied": [str(odds.implied(o)) for o in b.odds],
                "fair": [str(p) for p in fn(b.odds)], "method": b.method}
    except ValueError as e: raise HTTPException(422, {"code": "invalid_odds", "message": str(e)})

class SelIn(BaseModel):
    id: str; fixture: str = Field(max_length=200); market: str = Field(max_length=50)
    outcome: str = Field(max_length=50); odds: Decimal = Field(gt=1)

class Ticket(BaseModel):
    selections: list[SelIn] = Field(min_length=1, max_length=50)

def sels(t: Ticket): return [tk.Sel(s.id, s.fixture, s.market, s.outcome, s.odds) for s in t.selections]

@app.post("/api/v1/tickets/analyze")
def analyze(t: Ticket, _=Depends(auth.require_csrf)):
    s = sels(t)
    return {"combined_odds": tk.display_odds(tk.combined_odds(s)), "warnings": tk.validate(s),
            "caveat": "Combined odds multiply selection prices; any joint probability would assume independence."}

@app.post("/api/v1/tickets/export.csv", response_class=PlainTextResponse)
def export(t: Ticket, _=Depends(auth.require_csrf)): return tk.export_csv(sels(t))
