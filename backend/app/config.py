import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://chitcircle:chitcircle@localhost:5432/chitcircle")


def webhook_secret():
    """Shared secret for signed provider callbacks. Unset => every callback is rejected (fail safe)."""
    return os.getenv("WEBHOOK_SECRET")
