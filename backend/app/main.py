from contextlib import asynccontextmanager
from datetime import timedelta
import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    accounts,
    advice,
    assets,
    auth,
    backup,
    budgets,
    cash_flow,
    categories,
    categorization,
    crypto,
    dashboard,
    envelopes,
    exchange_rates,
    goals,
    insights,
    investments,
    net_worth,
    recurring,
    reports,
    settings as settings_routes,
    statement_imports,
    tags,
    transactions,
    workspaces,
)
from app.api.deps import require_finance_access
from app.core.config import APP_VERSION, Settings, get_settings
from app.db.seed import seed_default_account, seed_default_app_settings, seed_default_categories
from app.db.session import AsyncSessionLocal
from app.services.workspace_service import issue_initial_owner_bootstrap_code

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Authenticated installs seed only while atomically creating a personal
    # workspace. Global startup seeds would create ownerless financial rows.
    async with AsyncSessionLocal() as session:
        initial_owner_code = None
        if not app.state.settings.app_auth_required:
            await seed_default_categories(session)
            await seed_default_account(session)
        else:
            initial_owner_code = await issue_initial_owner_bootstrap_code(
                session,
                hmac_secret=app.state.settings.auth_hmac_secret.get_secret_value(),
                expires_in=timedelta(seconds=app.state.settings.initial_owner_bootstrap_ttl_seconds),
            )
        # App settings remain a deployment-wide singleton in this bounded
        # slice; unlike accounts/categories they are not financial ownership.
        await seed_default_app_settings(session)
        await session.commit()
        if initial_owner_code is not None:
            logger.warning(
                "Aurum initial-owner setup code (single use; expires in %s seconds): %s",
                app.state.settings.initial_owner_bootstrap_ttl_seconds,
                initial_owner_code,
            )
    yield


def create_app(app_settings: Settings | None = None) -> FastAPI:
    settings = app_settings or get_settings()
    configured_app = FastAPI(
        title="Aurum API",
        version=APP_VERSION,
        lifespan=lifespan,
        # Docs live under /api/* because nginx only proxies that prefix to the
        # backend (see frontend/nginx.conf) — everything else falls through to
        # the SPA's index.html, which is why the defaults (/docs, /openapi.json)
        # would silently 404 through the reverse proxy.
        # All three go away together when AURUM_ENABLE_DOCS=false — leaving
        # openapi.json reachable would keep handing out the full API map even
        # with the Swagger UI itself switched off.
        docs_url="/api/docs" if settings.docs_enabled else None,
        redoc_url="/api/redoc" if settings.docs_enabled else None,
        openapi_url="/api/openapi.json" if settings.docs_enabled else None,
    )
    configured_app.state.settings = settings

    # CORS stays off unless someone deliberately opens it, and credentials are
    # only granted to a pinned list. Starlette answers a credentialed "*" by
    # echoing back whatever Origin asked instead of a literal "*" — so the two
    # together turn any page the user happens to have open into an authenticated
    # client of their instance, which is exactly what the README's "fine if it's
    # only reachable from localhost" advice assumes can't happen.
    cors_origins = settings.cors_origins_list
    if cors_origins:
        configured_app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials="*" not in cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    configured_app.include_router(auth.router, prefix="/api")
    configured_app.include_router(workspaces.router, prefix="/api")
    protected = [Depends(require_finance_access)]
    for route in (
        dashboard,
        accounts,
        categories,
        categorization,
        transactions,
        assets,
        net_worth,
        backup,
        reports,
        insights,
        settings_routes,
        budgets,
        envelopes,
        advice,
        goals,
        recurring,
        cash_flow,
        tags,
        crypto,
        exchange_rates,
        investments,
        statement_imports,
    ):
        configured_app.include_router(route.router, prefix="/api", dependencies=protected)

    @configured_app.get("/api/health")
    async def health() -> dict[str, str]:
        # Status only. This is the one route nginx serves without auth (Docker's
        # HEALTHCHECK and uptime monitors need it — see frontend/nginx.conf), so
        # anything returned here is world-readable. The running version used to
        # ride along, which told an unauthenticated caller exactly which release
        # they were looking at, and therefore which known issues it still has;
        # it now comes back from GET /api/settings, which is behind auth.
        return {"status": "ok"}

    return configured_app


app = create_app()
