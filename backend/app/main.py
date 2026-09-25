from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.config import Settings, get_settings
from app.services.user_store import SQLiteUserStore


def create_app(
    settings: Settings | None = None,
    user_store: SQLiteUserStore | None = None,
) -> FastAPI:
    """Create the FastAPI application.

    Tests can pass isolated settings and a temporary user store. Production uses
    the configured settings and SQLite store.
    """
    app_settings = settings or get_settings()
    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.version,
        debug=app_settings.debug,
    )
    app.state.settings = app_settings
    app.state.user_store = user_store or SQLiteUserStore(app_settings.database_path)

    if app_settings.session_configured:
        app.add_middleware(
            SessionMiddleware,
            secret_key=app_settings.session_secret,
            https_only=app_settings.session_https_only,
            same_site="lax",
        )

    app.include_router(health_router)
    app.include_router(auth_router)
    return app


app = create_app()
