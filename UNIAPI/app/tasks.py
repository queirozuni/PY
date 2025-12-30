import asyncio
import shutil
import smtplib
import subprocess
import tempfile
import zipfile
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from sqlalchemy import select

from .db import AsyncSessionLocal, BackupSchedule, RestoreSchedule, EmailConfig, TaskRun

def _format_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")

def _run_subprocess(command: list[str], stdout=None, stdin=None) -> tuple[int, str]:
    result = subprocess.run(command, stdout=stdout, stdin=stdin, stderr=subprocess.PIPE, text=True, check=False)
    return result.returncode, result.stderr.strip()

def run_backup_sync(schedule: BackupSchedule) -> tuple[str, str, str | None]:
    backup_dir = Path(schedule.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _format_timestamp()
    sql_filename = f"BKP_{schedule.database}_{timestamp}.sql"
    zip_filename = f"BKP_{schedule.database}_{timestamp}.zip"
    sql_path = backup_dir / sql_filename
    zip_path = backup_dir / zip_filename

    dump_command = [
        "mysqldump",
        "-u",
        schedule.mysql_user,
        f"-p{schedule.mysql_pass}",
        schedule.database,
    ]
    with sql_path.open("w", encoding="utf-8") as sql_file:
        dump_code, dump_error = _run_subprocess(dump_command, stdout=sql_file)
    if dump_code != 0:
        sql_path.unlink(missing_ok=True)
        return "erro", f"Falha no mysqldump: {dump_error or 'erro desconhecido'}", None

    if schedule.zip_path:
        zip_command = [schedule.zip_path, "a", "-tzip", str(zip_path), str(sql_path)]
        zip_code, zip_error = _run_subprocess(zip_command)
        if zip_code != 0:
            sql_path.unlink(missing_ok=True)
            return "erro", f"Falha na compactação: {zip_error or 'erro desconhecido'}", None
    else:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.write(sql_path, arcname=sql_filename)

    sql_path.unlink(missing_ok=True)
    return "sucesso", f"Backup gerado em {zip_path}", str(zip_path)

def run_restore_sync(schedule: RestoreSchedule) -> tuple[str, str, str | None]:
    backup_path = Path(schedule.backup_path)
    if not backup_path.exists():
        return "erro", f"Arquivo de backup não encontrado: {backup_path}", None

    sql_path = backup_path
    temp_dir = None
    if backup_path.suffix.lower() == ".zip":
        temp_dir = Path(tempfile.mkdtemp(prefix="restore_"))
        with zipfile.ZipFile(backup_path, "r") as zip_file:
            zip_file.extractall(temp_dir)
        sql_files = list(temp_dir.glob("*.sql"))
        if not sql_files:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return "erro", "Nenhum arquivo .sql encontrado no zip.", None
        sql_path = sql_files[0]

    mysql_command = [
        "mysql",
        "-u",
        schedule.mysql_user,
        f"-p{schedule.mysql_pass}",
    ]
    if schedule.mysql_host:
        mysql_command.extend(["-h", schedule.mysql_host])
    mysql_command.append(schedule.target_database)

    with sql_path.open("r", encoding="utf-8") as sql_file:
        restore_code, restore_error = _run_subprocess(mysql_command, stdin=sql_file)

    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)

    if restore_code != 0:
        return "erro", f"Falha no restore: {restore_error or 'erro desconhecido'}", None

    return "sucesso", "Restore concluído com sucesso.", str(backup_path)

def send_status_email(config: EmailConfig, subject: str, body: str) -> tuple[bool, str]:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.sender
    recipients = [item.strip() for item in config.recipients.split(",") if item.strip()]
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    try:
        if config.use_tls:
            with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
                server.starttls()
                if config.smtp_user:
                    server.login(config.smtp_user, config.smtp_pass or "")
                server.send_message(message)
        else:
            with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port) as server:
                if config.smtp_user:
                    server.login(config.smtp_user, config.smtp_pass or "")
                server.send_message(message)
    except Exception as exc:
        return False, str(exc)

    return True, "Email enviado."

async def _fetch_email_config():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(EmailConfig).order_by(EmailConfig.id.desc()))
        return res.scalar_one_or_none()

async def execute_backup(schedule_id: int):
    async with AsyncSessionLocal() as session:
        schedule = await session.get(BackupSchedule, schedule_id)
        if not schedule or not schedule.enabled:
            return
        run = TaskRun(task_type="backup", schedule_id=schedule.id, started_at=datetime.utcnow())
        session.add(run)
        await session.commit()
        await session.refresh(run)

    status, message, output_path = await asyncio.to_thread(run_backup_sync, schedule)

    async with AsyncSessionLocal() as session:
        schedule = await session.get(BackupSchedule, schedule_id)
        run = await session.get(TaskRun, run.id)
        now = datetime.utcnow()
        if schedule:
            schedule.last_run_at = now
            schedule.last_status = status
            schedule.last_message = message
        if run:
            run.finished_at = now
            run.status = status
            run.message = message
            run.output_path = output_path
        await session.commit()

    config = await _fetch_email_config()
    if config:
        subject = f"Backup {schedule.name} - {status}"
        body = f"Tarefa: {schedule.name}\nStatus: {status}\nDetalhes: {message}"
        await asyncio.to_thread(send_status_email, config, subject, body)

async def execute_restore(schedule_id: int):
    async with AsyncSessionLocal() as session:
        schedule = await session.get(RestoreSchedule, schedule_id)
        if not schedule or not schedule.enabled:
            return
        run = TaskRun(task_type="restore", schedule_id=schedule.id, started_at=datetime.utcnow())
        session.add(run)
        await session.commit()
        await session.refresh(run)

    status, message, output_path = await asyncio.to_thread(run_restore_sync, schedule)

    async with AsyncSessionLocal() as session:
        schedule = await session.get(RestoreSchedule, schedule_id)
        run = await session.get(TaskRun, run.id)
        now = datetime.utcnow()
        if schedule:
            schedule.last_run_at = now
            schedule.last_status = status
            schedule.last_message = message
        if run:
            run.finished_at = now
            run.status = status
            run.message = message
            run.output_path = output_path
        await session.commit()

    config = await _fetch_email_config()
    if config:
        subject = f"Restore {schedule.name} - {status}"
        body = f"Tarefa: {schedule.name}\nStatus: {status}\nDetalhes: {message}"
        await asyncio.to_thread(send_status_email, config, subject, body)

def _should_run(schedule, now: datetime) -> bool:
    if not schedule.enabled:
        return False
    if now.hour != schedule.cron_hour or now.minute != schedule.cron_minute:
        return False
    if not schedule.last_run_at:
        return True
    last = schedule.last_run_at
    return (last.date(), last.hour, last.minute) != (now.date(), now.hour, now.minute)

async def scheduler_loop():
    while True:
        now = datetime.utcnow()
        async with AsyncSessionLocal() as session:
            backups = (await session.execute(select(BackupSchedule))).scalars().all()
            restores = (await session.execute(select(RestoreSchedule))).scalars().all()

        for schedule in backups:
            if _should_run(schedule, now):
                asyncio.create_task(execute_backup(schedule.id))
        for schedule in restores:
            if _should_run(schedule, now):
                asyncio.create_task(execute_restore(schedule.id))

        await asyncio.sleep(30)
