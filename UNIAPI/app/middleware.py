from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.cors import CORSMiddleware
from .settings import settings

def setup_middlewares(app):
    allow = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow or ["*"],
        allow_credentials=True,
        allow_methods=["GET","POST"],
        allow_headers=["*"],
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY,
        https_only=True,
        same_site="lax",
        max_age=60*60*8,
    )
