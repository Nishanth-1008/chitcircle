import os
from dotenv import load_dotenv

load_dotenv()

import redis

# Secrets that must never ship with an insecure default once we are in production.
_INSECURE_DEFAULTS = {
    "JWT_SECRET_KEY": "dev-secret-change-in-production",
}


def _get_env() -> dict:
    return {
        "DATABASE_URL": os.getenv("DATABASE_URL", "postgresql+psycopg://chitcircle:chitcircle@localhost:5432/chitcircle"),
        "WEBHOOK_SECRET": os.getenv("WEBHOOK_SECRET"),
        # PayPal Sandbox Configuration
        "PAYPAL_CLIENT_ID": os.getenv("PAYPAL_CLIENT_ID"),
        "PAYPAL_CLIENT_SECRET": os.getenv("PAYPAL_CLIENT_SECRET"),
        "PAYPAL_BASE_URL": os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com"),
        "PAYPAL_WEBHOOK_ID": os.getenv("PAYPAL_WEBHOOK_ID"),
        # JWT Configuration — no insecure default; must be set explicitly (§11.1, gap #11).
        "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY"),
        "JWT_ALGORITHM": os.getenv("JWT_ALGORITHM", "HS256"),
        "JWT_EXPIRATION_MINUTES": int(os.getenv("JWT_EXPIRATION_MINUTES", "15")),
        # Redis
        "REDIS_URL": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        # Runtime
        "APP_ENV": os.getenv("APP_ENV", "development"),
        # Read replica URL for read endpoints (optional; production only).
        # Empty means use DATABASE_URL for all reads.
        "READ_REPLICA_DATABASE_URL": os.getenv("READ_REPLICA_DATABASE_URL", ""),
        # The X-Actor-Id / X-Actor-Role stub: test + local web client only, never production.
        "ALLOW_ACTOR_HEADERS": os.getenv("ALLOW_ACTOR_HEADERS", "true"),
        # Feature switches (see §13.4): kill switches for agent proposal / mandate execution.
        "AGENT_PROPOSAL_ENABLED": os.getenv("AGENT_PROPOSAL_ENABLED", "true"),
        "AGENT_EXECUTION_ENABLED": os.getenv("AGENT_EXECUTION_ENABLED", "true"),
    }


def get_env(key: str, default: str | None = None) -> str | None:
    return _get_env().get(key, default)


def database_url() -> str:
    return _get_env()["DATABASE_URL"]


def webhook_secret() -> str | None:
    return _get_env()["WEBHOOK_SECRET"]


def paypal_client_id() -> str | None:
    return _get_env()["PAYPAL_CLIENT_ID"]


def paypal_client_secret() -> str | None:
    return _get_env()["PAYPAL_CLIENT_SECRET"]


def paypal_base_url() -> str:
    return _get_env()["PAYPAL_BASE_URL"]


def paypal_webhook_id() -> str | None:
    return _get_env()["PAYPAL_WEBHOOK_ID"]


def jwt_secret_key() -> str:
    value = _get_env()["JWT_SECRET_KEY"]
    if not value or value == "dev-secret-change-in-production":
        raise RuntimeError("JWT_SECRET_KEY must be set to a secure value; insecure default removed (gap #11)")
    return value


def jwt_algorithm() -> str:
    return _get_env()["JWT_ALGORITHM"]


def jwt_expiration_minutes() -> int:
    return _get_env()["JWT_EXPIRATION_MINUTES"]


def redis_url() -> str:
    return _get_env()["REDIS_URL"]


_redis_client = None


def get_redis():
    """Shared Redis client (lazy singleton). Used for caching, rate limiting, token cache."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(redis_url(), decode_responses=True)
    return _redis_client


def read_replica_url() -> str:
    """Read-replica database URL. Empty string means use DATABASE_URL for all reads."""
    return _get_env()["READ_REPLICA_DATABASE_URL"]


def encryption_key() -> str | None:
    """Base64-encoded 32-byte key for field-level encryption of PII (§13)."""
    return os.getenv("ENCRYPTION_KEY")


def app_env() -> str:
    """deployment environment: development | test | staging | production"""
    return _get_env()["APP_ENV"]


def is_production() -> bool:
    return app_env().strip().lower() in ("production", "prod")


def allow_actor_headers() -> bool:
    """Whether the ``X-Actor-Id``/``X-Actor-Role`` development stub may identify a caller.

    Always off in production, whatever the flag says: a deployed instance must only accept a
    verified Bearer token (gap #11).
    """
    if is_production():
        return False
    return _get_env()["ALLOW_ACTOR_HEADERS"].strip().lower() in ("1", "true", "yes")


def config_problems() -> list:
    """Fatal configuration problems. Production must not boot with any of these.

    Returns an empty list in development, where insecure defaults are deliberate.
    """
    if not is_production():
        return []
    env = _get_env()
    problems = []
    for key, insecure_value in _INSECURE_DEFAULTS.items():
        value = env.get(key)
        if not value or value == insecure_value:
            problems.append(f"{key} is unset or still the insecure development default")
    if not env.get("WEBHOOK_SECRET"):
        problems.append("WEBHOOK_SECRET is required in production")
    return problems


def assert_secure_config() -> None:
    """Refuse to start with an insecure production configuration (§16.6)."""
    problems = config_problems()
    if problems:
        raise RuntimeError("refusing to start with an insecure configuration: " + "; ".join(problems))
