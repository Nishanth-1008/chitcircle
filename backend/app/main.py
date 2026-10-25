from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from financial_engine.errors import FinancialEngineError

from . import db
from .api.routes import router
from .errors import ServiceError
from .models import LedgerImmutableError


@asynccontextmanager
async def lifespan(app: FastAPI):
    if db.SessionLocal is None:
        db.init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="ChitCircle Financial Engine", version="1.0", lifespan=lifespan)

    @app.exception_handler(ServiceError)
    async def _svc(_: Request, exc: ServiceError):
        return JSONResponse(status_code=exc.status, content={"code": exc.code, "detail": exc.detail, **exc.extra})

    @app.exception_handler(FinancialEngineError)
    async def _engine(_: Request, exc: FinancialEngineError):
        return JSONResponse(status_code=422, content={"code": type(exc).__name__, "detail": str(exc)})

    @app.exception_handler(LedgerImmutableError)
    async def _immut(_: Request, exc: LedgerImmutableError):
        return JSONResponse(status_code=409, content={"code": "LEDGER_IMMUTABLE", "detail": str(exc)})

    app.include_router(router)
    return app


app = create_app()
