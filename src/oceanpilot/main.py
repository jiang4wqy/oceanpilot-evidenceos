from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI

from oceanpilot.adapters.persistence.sqlite import (
    SqliteCaseStoreFactory,
    initialize_schema,
)
from oceanpilot.api.cases import router as cases_router
from oceanpilot.api.errors import register_exception_handlers
from oceanpilot.api.health import router as health_router
from oceanpilot.application.case_service import CaseService
from oceanpilot.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()
    store_factory = SqliteCaseStoreFactory(resolved.db_path)
    case_service = CaseService(
        store_factory,
        clock=lambda: datetime.now(UTC),
        uuid_factory=lambda: str(uuid4()),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        initialize_schema(resolved.db_path)
        with store_factory() as store:
            store.healthcheck()
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.settings = resolved
    app.state.store_factory = store_factory
    app.state.case_service = case_service
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(cases_router)
    return app
