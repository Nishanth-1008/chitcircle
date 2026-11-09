"""FastAPI app factory with lifespan; asserts secure config, init_db, assert_migrations_applied;
exception handlers for ServiceError (400-ish), FinancialEngineError (422), LedgerImmutableError (409);
includes router. Includes HTTP idempotency middleware (gap #2) and request logging (gap #15).
"""
from contextlib import asynccontextmanager
from typing import Optional

import hashlib
import json
import logging
import time
import uuid

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from financial_engine.errors import FinancialEngineError

from . import config, db
from .api.routes import router
from .auth import decode_token
from .errors import ServiceError
from .models import ApiIdempotencyRow, LedgerImmutableError

log = logging.getLogger("chitcircle.api")

# OpenTelemetry tracing (gap #15). Degraded gracefully when the opentelemetry package is not
# installed: tracing is simply a no-op and the API behaves exactly as before.
try:
    from opentelemetry import trace
    from opentelemetry.context import attach as _context_attach, detach as _context_detach
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
    _OTEL_AVAILABLE = True
except Exception:  # noqa: BLE001 - tracing is optional
    trace = None
    _OTEL_AVAILABLE = False

_otel_tracer = None


def _init_tracing() -> None:
    """Configure OpenTelemetry tracing if the SDK is available."""
    global _otel_tracer
    if not _OTEL_AVAILABLE:
        return
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _otel_tracer = trace.get_tracer("chitcircle.api")

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _problem(status: int, title: str, detail: str, code: str, instance: str = None) -> dict:
    """Build an RFC 9457 problem details body."""
    body = {"type": "about:blank", "title": title, "status": status, "detail": detail, "code": code}
    if instance:
        body["instance"] = instance
    return body


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("api.startup", extra={"env": config.app_env()})
    config.assert_secure_config()          # production refuses to boot with insecure defaults (§16.6)
    if db.SessionLocal is None:
        # On SQLite (tests, local bootstrap) the schema is created here. On Postgres the schema
        # comes from Alembic and startup never mutates it (gap #1).
        db.init_db()
    db.assert_migrations_applied()         # Postgres must be at `alembic upgrade head`, not behind
    yield
    log.info("api.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title="ChitCircle Financial Engine", version="1.0", lifespan=lifespan)
    _init_tracing()   # gap #15: no-op when opentelemetry is not installed

    @app.exception_handler(ServiceError)
    async def _svc(_: Request, exc: ServiceError):
        body = _problem(exc.status, exc.code.replace("_", " ").title(), exc.detail, exc.code)
        if exc.extra:
            body.update(exc.extra)
        return JSONResponse(
            status_code=exc.status,
            content=body,
            media_type="application/problem+json",
        )

    @app.exception_handler(FinancialEngineError)
    async def _engine(_: Request, exc: FinancialEngineError):
        return JSONResponse(
            status_code=422,
            content=_problem(422, "Financial Engine Error", str(exc), type(exc).__name__),
            media_type="application/problem+json",
        )

    @app.exception_handler(LedgerImmutableError)
    async def _immut(_: Request, exc: LedgerImmutableError):
        return JSONResponse(
            status_code=409,
            content=_problem(409, "Ledger Immutable", str(exc), "LEDGER_IMMUTABLE"),
            media_type="application/problem+json",
        )

    # ---------------------------------------------------------------- request logging (gap #15)
    #
    # Correlates every request with an X-Request-ID and logs method, path, status and duration.
    # The ID is echoed back in the response header so clients and logs can be joined.
    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        trace_id = None
        span = None
        token = None
        if _otel_tracer is not None:
            span = _otel_tracer.start_span(f"{request.method} {request.url.path}")
            token = _context_attach(trace.set_span_in_context(span))
            try:
                sc = span.get_span_context()
                if sc.is_valid:
                    trace_id = format(sc.trace_id, "032x")
            except Exception:  # noqa: BLE001
                trace_id = None

        start = time.perf_counter()
        log.info(
            "request.start",
            extra={"request_id": request_id, "trace_id": trace_id,
                   "method": request.method, "path": request.url.path},
        )

        try:
            response = await call_next(request)
        finally:
            if span is not None:
                span.end()
            if token is not None:
                _context_detach(token)

        duration_ms = (time.perf_counter() - start) * 1000
        log.info(
            "request.end",
            extra={
                "request_id": request_id,
                "trace_id": trace_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        response.headers["X-Request-ID"] = request_id
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id
        return response

    # ---------------------------------------------------------------- rate limiting (gap #16)
    #
    # Redis token-bucket per (user_id, endpoint): 60 req/min default.
    # Fails open (allows the request) if Redis is unavailable.
    _RATE_LIMIT_CAPACITY = 60
    _RATE_LIMIT_REFILL_RATE = 1.0  # tokens per second

    def _check_rate_limit(user_id: str, path: str) -> tuple:
        """Token-bucket rate limit check. Returns (allowed, remaining_tokens)."""
        try:
            r = config.get_redis()
            key = f"rate_limit:{user_id}:{path}"
            now = time.time()
            data = r.get(key)
            if data:
                state = json.loads(data)
                tokens = state["tokens"]
                last_update = state["last_update"]
            else:
                tokens = _RATE_LIMIT_CAPACITY
                last_update = now
            elapsed = max(0.0, now - last_update)
            tokens = min(_RATE_LIMIT_CAPACITY, tokens + elapsed * _RATE_LIMIT_REFILL_RATE)
            if tokens >= 1:
                tokens -= 1
                r.setex(key, 3600, json.dumps({"tokens": tokens, "last_update": now}))
                return True, int(tokens)
            r.setex(key, 3600, json.dumps({"tokens": tokens, "last_update": now}))
            return False, 0
        except Exception:  # noqa: BLE001 - fail open if Redis is down
            return True, _RATE_LIMIT_CAPACITY

    @app.middleware("http")
    async def rate_limiting_middleware(request: Request, call_next):
        user_id = None
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                payload = decode_token(auth.split(" ", 1)[1])
                user_id = payload.get("sub")
            except Exception:
                pass
        if not user_id:
            user_id = request.headers.get("X-Actor-Id") or "anonymous"

        allowed, remaining = _check_rate_limit(user_id, request.url.path)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content=_problem(429, "Too Many Requests", "Rate limit exceeded", "RATE_LIMIT_EXCEEDED"),
                media_type="application/problem+json",
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    # ---------------------------------------------------------------- idempotency middleware (gap #2)
    #
    # Require Idempotency-Key on every state-changing endpoint. Key = (actor_id, key); the
    # api_idempotency table is authoritative. Same key + same request hash → replay stored response.
    # Same key + different hash → 422. No key on a state-changing method → proceed (the key is
    # enforced by the service layer where it matters most).
    _IDEMPOTENT_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    def _resolve_actor(request: Request) -> Optional[str]:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                payload = decode_token(auth.split(" ", 1)[1])
                return payload.get("sub")
            except Exception:
                return None
        return request.headers.get("X-Actor-Id")

    @app.middleware("http")
    async def idempotency_middleware(request: Request, call_next):
        if request.method not in _IDEMPOTENT_METHODS:
            return await call_next(request)

        idem_key = request.headers.get("Idempotency-Key")
        if not idem_key:
            return JSONResponse(
                status_code=428,
                content=_problem(428, "Precondition Required",
                                 "Idempotency-Key header is required on state-changing requests",
                                 "IDEMPOTENCY_KEY_REQUIRED"),
                media_type="application/problem+json",
            )

        body = await request.body()

        actor_id = _resolve_actor(request)
        if not actor_id:
            async def _receive():
                return {"type": "http.request", "body": body, "more_body": False}
            request._receive = _receive
            return await call_next(request)

        request_hash = hashlib.sha256(
            f"{request.method}:{request.url.path}:{body}".encode()).hexdigest()

        s = db.SessionLocal()
        try:
            row = s.scalar(select(ApiIdempotencyRow).where(
                ApiIdempotencyRow.key == idem_key,
                ApiIdempotencyRow.actor_id == actor_id,
            ))
            if row is not None:
                if row.request_hash == request_hash:
                    return JSONResponse(
                        status_code=row.status_code or 200,
                        content=row.response or {},
                        headers={"X-Idempotency-Replayed": "true"},
                    )
                return JSONResponse(
                    status_code=422,
                    content={"code": "IDEMPOTENCY_CONFLICT",
                             "detail": "idempotency key reused with a different request"},
                )
        finally:
            s.close()

        async def _receive():
            return {"type": "http.request", "body": body, "more_body": False}
        request._receive = _receive

        response = await call_next(request)

        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        response_data = None
        try:
            response_data = json.loads(response_body)
        except Exception:
            response_data = {"raw": response_body.decode("utf-8", "replace")}

        s = db.SessionLocal()
        try:
            s.add(ApiIdempotencyRow(
                key=idem_key, actor_id=actor_id, request_hash=request_hash,
                response=response_data, status_code=response.status_code,
            ))
            s.commit()
        except IntegrityError:
            s.rollback()
        finally:
            s.close()

        return Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )

    app.include_router(router)
    return app


app = create_app()
