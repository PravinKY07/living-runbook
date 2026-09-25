from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.repositories import router as repositories_router
from app.api.runbooks import router as runbooks_router
from app.config import Settings, get_settings
from app.services.analysis_jobs import AnalysisJobManager
from app.services.audit_store import SQLiteAuditStore
from app.services.job_store import SQLiteJobStore
from app.services.runbook_store import SQLiteRunbookStore
from app.services.user_store import SQLiteUserStore


def create_app(
    settings: Settings | None = None,
    user_store: SQLiteUserStore | None = None,
    runbook_store: SQLiteRunbookStore | None = None,
    job_manager: AnalysisJobManager | None = None,
) -> FastAPI:
    """Create the FastAPI application.

    Tests can pass isolated settings and stores. Production uses SQLite on the
    configured persistent path and a single in-process analysis worker.
    """
    app_settings = settings or get_settings()
    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.version,
        debug=app_settings.debug,
    )
    app.state.settings = app_settings
    app.state.user_store = user_store or SQLiteUserStore(app_settings.database_path)
    app.state.runbook_store = runbook_store or SQLiteRunbookStore(app_settings.database_path)
    app.state.audit_store = SQLiteAuditStore(app_settings.database_path)
    app.state.job_manager = job_manager or AnalysisJobManager(
        job_store=SQLiteJobStore(app_settings.database_path),
        runbook_store=app.state.runbook_store,
        audit_store=app.state.audit_store,
    )

    if app_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app_settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    if app_settings.session_configured:
        app.add_middleware(
            SessionMiddleware,
            secret_key=app_settings.session_secret,
            https_only=app_settings.session_https_only,
            same_site=app_settings.session_same_site,
        )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(repositories_router)
    app.include_router(jobs_router)
    app.include_router(runbooks_router)
    app.include_router(audit_router)
    return app


app = create_app()
