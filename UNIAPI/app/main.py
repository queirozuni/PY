import asyncio
from datetime import datetime

from fastapi import FastAPI, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeSerializer
from pathlib import Path
import secrets
from sqlalchemy import select, desc

from .middleware import setup_middlewares
from .settings import settings
from .db import (
    init_db,
    AsyncSessionLocal,
    get_user_by_username,
    BackupSchedule,
    RestoreSchedule,
    EmailConfig,
    TaskRun,
)
from .auth import verify_password
from .tasks import scheduler_loop, execute_backup, execute_restore

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

def _require_login(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return None, RedirectResponse("/login", status_code=status.HTTP_302_FOUND)
    return uid, None

@app.on_event("startup")
async def startup():
    (BASE_DIR / ".." / "data").resolve().mkdir(parents=True, exist_ok=True)
    await init_db()
    app.state.scheduler = asyncio.create_task(scheduler_loop())

@app.on_event("shutdown")
async def shutdown():
    task = getattr(app.state, "scheduler", None)
    if task:
        task.cancel()

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
    uid, redirect = _require_login(request)
    if redirect:
        return redirect
    async with AsyncSessionLocal() as session:
        runs = (await session.execute(select(TaskRun).order_by(desc(TaskRun.started_at)).limit(5))).scalars().all()
    return templates.TemplateResponse("home.html", {"request": request, "user": uid, "runs": runs})

@app.get("/backup-schedules", response_class=HTMLResponse)
async def backup_schedules(request: Request):
    uid, redirect = _require_login(request)
    if redirect:
        return redirect
    async with AsyncSessionLocal() as session:
        schedules = (await session.execute(select(BackupSchedule).order_by(BackupSchedule.created_at.desc()))).scalars().all()
    return templates.TemplateResponse(
        "backup_schedules.html",
        {"request": request, "user": uid, "schedules": schedules, "csrf_token": _ensure_csrf(request)},
    )

@app.post("/backup-schedules")
async def create_backup_schedule(
    request: Request,
    name: str = Form(...),
    database: str = Form(...),
    mysql_user: str = Form(...),
    mysql_pass: str = Form(...),
    backup_dir: str = Form(...),
    zip_path: str = Form(""),
    cron_hour: int = Form(...),
    cron_minute: int = Form(...),
    enabled: str | None = Form(None),
    csrf_token: str = Form(...),
):
    _, redirect = _require_login(request)
    if redirect:
        return redirect
    if not _check_csrf(request, csrf_token):
        return RedirectResponse("/backup-schedules", status_code=status.HTTP_303_SEE_OTHER)
    async with AsyncSessionLocal() as session:
        schedule = BackupSchedule(
            name=name,
            database=database,
            mysql_user=mysql_user,
            mysql_pass=mysql_pass,
            backup_dir=backup_dir,
            zip_path=zip_path or None,
            cron_hour=cron_hour,
            cron_minute=cron_minute,
            enabled=bool(enabled),
        )
        session.add(schedule)
        await session.commit()
    return RedirectResponse("/backup-schedules", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/backup-schedules/{schedule_id}", response_class=HTMLResponse)
async def edit_backup_schedule(request: Request, schedule_id: int):
    uid, redirect = _require_login(request)
    if redirect:
        return redirect
    async with AsyncSessionLocal() as session:
        schedule = await session.get(BackupSchedule, schedule_id)
    if not schedule:
        return RedirectResponse("/backup-schedules", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "backup_schedule_edit.html",
        {"request": request, "user": uid, "schedule": schedule, "csrf_token": _ensure_csrf(request)},
    )

@app.post("/backup-schedules/{schedule_id}")
async def update_backup_schedule(
    request: Request,
    schedule_id: int,
    name: str = Form(...),
    database: str = Form(...),
    mysql_user: str = Form(...),
    mysql_pass: str = Form(...),
    backup_dir: str = Form(...),
    zip_path: str = Form(""),
    cron_hour: int = Form(...),
    cron_minute: int = Form(...),
    enabled: str | None = Form(None),
    csrf_token: str = Form(...),
):
    _, redirect = _require_login(request)
    if redirect:
        return redirect
    if not _check_csrf(request, csrf_token):
        return RedirectResponse(f"/backup-schedules/{schedule_id}", status_code=status.HTTP_303_SEE_OTHER)
    async with AsyncSessionLocal() as session:
        schedule = await session.get(BackupSchedule, schedule_id)
        if schedule:
            schedule.name = name
            schedule.database = database
            schedule.mysql_user = mysql_user
            schedule.mysql_pass = mysql_pass
            schedule.backup_dir = backup_dir
            schedule.zip_path = zip_path or None
            schedule.cron_hour = cron_hour
            schedule.cron_minute = cron_minute
            schedule.enabled = bool(enabled)
            await session.commit()
    return RedirectResponse("/backup-schedules", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/backup-schedules/{schedule_id}/run")
async def run_backup_now(request: Request, schedule_id: int, csrf_token: str = Form(...)):
    _, redirect = _require_login(request)
    if redirect:
        return redirect
    if not _check_csrf(request, csrf_token):
        return RedirectResponse("/backup-schedules", status_code=status.HTTP_303_SEE_OTHER)
    asyncio.create_task(execute_backup(schedule_id))
    return RedirectResponse("/backup-schedules", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/restore-schedules", response_class=HTMLResponse)
async def restore_schedules(request: Request):
    uid, redirect = _require_login(request)
    if redirect:
        return redirect
    async with AsyncSessionLocal() as session:
        schedules = (await session.execute(select(RestoreSchedule).order_by(RestoreSchedule.created_at.desc()))).scalars().all()
    return templates.TemplateResponse(
        "restore_schedules.html",
        {"request": request, "user": uid, "schedules": schedules, "csrf_token": _ensure_csrf(request)},
    )

@app.post("/restore-schedules")
async def create_restore_schedule(
    request: Request,
    name: str = Form(...),
    backup_path: str = Form(...),
    target_database: str = Form(...),
    mysql_user: str = Form(...),
    mysql_pass: str = Form(...),
    mysql_host: str = Form(""),
    cron_hour: int = Form(...),
    cron_minute: int = Form(...),
    enabled: str | None = Form(None),
    csrf_token: str = Form(...),
):
    _, redirect = _require_login(request)
    if redirect:
        return redirect
    if not _check_csrf(request, csrf_token):
        return RedirectResponse("/restore-schedules", status_code=status.HTTP_303_SEE_OTHER)
    async with AsyncSessionLocal() as session:
        schedule = RestoreSchedule(
            name=name,
            backup_path=backup_path,
            target_database=target_database,
            mysql_user=mysql_user,
            mysql_pass=mysql_pass,
            mysql_host=mysql_host or None,
            cron_hour=cron_hour,
            cron_minute=cron_minute,
            enabled=bool(enabled),
        )
        session.add(schedule)
        await session.commit()
    return RedirectResponse("/restore-schedules", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/restore-schedules/{schedule_id}", response_class=HTMLResponse)
async def edit_restore_schedule(request: Request, schedule_id: int):
    uid, redirect = _require_login(request)
    if redirect:
        return redirect
    async with AsyncSessionLocal() as session:
        schedule = await session.get(RestoreSchedule, schedule_id)
    if not schedule:
        return RedirectResponse("/restore-schedules", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "restore_schedule_edit.html",
        {"request": request, "user": uid, "schedule": schedule, "csrf_token": _ensure_csrf(request)},
    )

@app.post("/restore-schedules/{schedule_id}")
async def update_restore_schedule(
    request: Request,
    schedule_id: int,
    name: str = Form(...),
    backup_path: str = Form(...),
    target_database: str = Form(...),
    mysql_user: str = Form(...),
    mysql_pass: str = Form(...),
    mysql_host: str = Form(""),
    cron_hour: int = Form(...),
    cron_minute: int = Form(...),
    enabled: str | None = Form(None),
    csrf_token: str = Form(...),
):
    _, redirect = _require_login(request)
    if redirect:
        return redirect
    if not _check_csrf(request, csrf_token):
        return RedirectResponse(f"/restore-schedules/{schedule_id}", status_code=status.HTTP_303_SEE_OTHER)
    async with AsyncSessionLocal() as session:
        schedule = await session.get(RestoreSchedule, schedule_id)
        if schedule:
            schedule.name = name
            schedule.backup_path = backup_path
            schedule.target_database = target_database
            schedule.mysql_user = mysql_user
            schedule.mysql_pass = mysql_pass
            schedule.mysql_host = mysql_host or None
            schedule.cron_hour = cron_hour
            schedule.cron_minute = cron_minute
            schedule.enabled = bool(enabled)
            await session.commit()
    return RedirectResponse("/restore-schedules", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/restore-schedules/{schedule_id}/run")
async def run_restore_now(request: Request, schedule_id: int, csrf_token: str = Form(...)):
    _, redirect = _require_login(request)
    if redirect:
        return redirect
    if not _check_csrf(request, csrf_token):
        return RedirectResponse("/restore-schedules", status_code=status.HTTP_303_SEE_OTHER)
    asyncio.create_task(execute_restore(schedule_id))
    return RedirectResponse("/restore-schedules", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/email-config", response_class=HTMLResponse)
async def email_config(request: Request):
    uid, redirect = _require_login(request)
    if redirect:
        return redirect
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(EmailConfig).order_by(EmailConfig.id.desc()))
        config = res.scalar_one_or_none()
    return templates.TemplateResponse(
        "email_config.html",
        {"request": request, "user": uid, "config": config, "csrf_token": _ensure_csrf(request)},
    )

@app.post("/email-config")
async def save_email_config(
    request: Request,
    smtp_host: str = Form(...),
    smtp_port: int = Form(...),
    smtp_user: str = Form(""),
    smtp_pass: str = Form(""),
    sender: str = Form(...),
    recipients: str = Form(...),
    use_tls: str | None = Form(None),
    csrf_token: str = Form(...),
):
    _, redirect = _require_login(request)
    if redirect:
        return redirect
    if not _check_csrf(request, csrf_token):
        return RedirectResponse("/email-config", status_code=status.HTTP_303_SEE_OTHER)
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(EmailConfig).order_by(EmailConfig.id.desc()))
        config = res.scalar_one_or_none()
        if config:
            config.smtp_host = smtp_host
            config.smtp_port = smtp_port
            config.smtp_user = smtp_user or None
            config.smtp_pass = smtp_pass or None
            config.sender = sender
            config.recipients = recipients
            config.use_tls = bool(use_tls)
            config.updated_at = datetime.utcnow()
        else:
            session.add(EmailConfig(
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                smtp_user=smtp_user or None,
                smtp_pass=smtp_pass or None,
                sender=sender,
                recipients=recipients,
                use_tls=bool(use_tls),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            ))
        await session.commit()
    return RedirectResponse("/email-config", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/runs", response_class=HTMLResponse)
async def task_runs(request: Request):
    uid, redirect = _require_login(request)
    if redirect:
        return redirect
    async with AsyncSessionLocal() as session:
        runs = (await session.execute(select(TaskRun).order_by(desc(TaskRun.started_at)).limit(50))).scalars().all()
    return templates.TemplateResponse(
        "task_runs.html",
        {"request": request, "user": uid, "runs": runs},
    )
