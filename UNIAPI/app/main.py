from fastapi import FastAPI, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeSerializer
from pathlib import Path
import secrets

from .middleware import setup_middlewares
from .settings import settings
from .db import init_db, AsyncSessionLocal, get_user_by_username
from .auth import verify_password

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="UniApi Login")
setup_middlewares(app)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

_serializer = URLSafeSerializer(settings.SECRET_KEY, salt="csrf")

def _ensure_csrf(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return _serializer.dumps(token)

def _check_csrf(request: Request, token_received: str) -> bool:
    try:
        token_raw = _serializer.loads(token_received)
    except Exception:
        return False
    return token_raw == request.session.get("csrf_token")

@app.on_event("startup")
async def startup():
    (BASE_DIR / ".." / "data").resolve().mkdir(parents=True, exist_ok=True)
    await init_db()

@app.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    if request.session.get("uid"):
        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request, "csrf_token": _ensure_csrf(request), "error": None})

@app.post("/login")
async def post_login(request: Request, username: str = Form(...), password: str = Form(...), csrf_token: str = Form(...)):
    if not _check_csrf(request, csrf_token):
        return templates.TemplateResponse("login.html", {"request": request, "csrf_token": _ensure_csrf(request), "error": "Sessão expirada."})
    async with AsyncSessionLocal() as session:
        user = await get_user_by_username(session, username)
        if not user or not user.is_active or not verify_password(user.password_hash, password):
            return templates.TemplateResponse("login.html", {"request": request, "csrf_token": _ensure_csrf(request), "error": "Usuário ou senha inválidos."})
    request.session["uid"] = username
    request.session.pop("csrf_token", None)
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("home.html", {"request": request, "user": uid})
