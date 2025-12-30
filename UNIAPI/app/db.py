from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from datetime import datetime
from .settings import settings
from .auth import hash_password

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class BackupSchedule(Base):
    __tablename__ = "backup_schedules"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    database = Column(String(120), nullable=False)
    mysql_user = Column(String(120), nullable=False)
    mysql_pass = Column(String(200), nullable=False)
    backup_dir = Column(String(255), nullable=False)
    zip_path = Column(String(255), nullable=True)
    cron_hour = Column(Integer, nullable=False)
    cron_minute = Column(Integer, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(DateTime, nullable=True)
    last_status = Column(String(20), nullable=True)
    last_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class RestoreSchedule(Base):
    __tablename__ = "restore_schedules"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    backup_path = Column(String(255), nullable=False)
    target_database = Column(String(120), nullable=False)
    mysql_user = Column(String(120), nullable=False)
    mysql_pass = Column(String(200), nullable=False)
    mysql_host = Column(String(120), nullable=True)
    cron_hour = Column(Integer, nullable=False)
    cron_minute = Column(Integer, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(DateTime, nullable=True)
    last_status = Column(String(20), nullable=True)
    last_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class EmailConfig(Base):
    __tablename__ = "email_config"
    id = Column(Integer, primary_key=True)
    smtp_host = Column(String(120), nullable=False)
    smtp_port = Column(Integer, nullable=False, default=587)
    smtp_user = Column(String(120), nullable=True)
    smtp_pass = Column(String(200), nullable=True)
    sender = Column(String(160), nullable=False)
    recipients = Column(Text, nullable=False)
    use_tls = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class TaskRun(Base):
    __tablename__ = "task_runs"
    id = Column(Integer, primary_key=True)
    task_type = Column(String(20), nullable=False)
    schedule_id = Column(Integer, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=True)
    message = Column(Text, nullable=True)
    output_path = Column(String(255), nullable=True)

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.username == settings.ADMIN_USER))
        if not res.scalar_one_or_none():
            session.add(User(
                username=settings.ADMIN_USER,
                password_hash=hash_password(settings.ADMIN_PASS),
                is_active=True,
            ))
            await session.commit()

async def get_user_by_username(session: AsyncSession, username: str):
    res = await session.execute(select(User).where(User.username == username))
    return res.scalar_one_or_none()
