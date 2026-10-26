import os
from dotenv import load_dotenv

load_dotenv()


def _get_env() -> dict:
    return {
        "DATABASE_URL": os.getenv("DATABASE_URL", "postgresql+psycopg://chitcircle:chitcircle@localhost:5432/chitcircle"),
        "WEBHOOK_SECRET": os.getenv("WEBHOOK_SECRET"),
        # PayPal Sandbox Configuration
        "PAYPAL_CLIENT_ID": os.getenv("PAYPAL_CLIENT_ID"),
        "PAYPAL_CLIENT_SECRET": os.getenv("PAYPAL_CLIENT_SECRET"),
        "PAYPAL_BASE_URL": os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com"),
        "PAYPAL_WEBHOOK_ID": os.getenv("PAYPAL_WEBHOOK_ID"),
        # JWT Configuration
        "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production"),
        "JWT_ALGORITHM": os.getenv("JWT_ALGORITHM", "HS256"),
        "JWT_EXPIRATION_MINUTES": int(os.getenv("JWT_EXPIRATION_MINUTES", "60")),
        # Redis
        "REDIS_URL": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
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
    return _get_env()["JWT_SECRET_KEY"]


def jwt_algorithm() -> str:
    return _get_env()["JWT_ALGORITHM"]


def jwt_expiration_minutes() -> int:
    return _get_env()["JWT_EXPIRATION_MINUTES"]


def redis_url() -> str:
    return _get_env()["REDIS_URL"]
