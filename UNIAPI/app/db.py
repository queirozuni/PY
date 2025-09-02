from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Boolean, DateTime, select
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
