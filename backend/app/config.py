import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chitcircle.db")


def webhook_secret():
    """Shared secret for signed provider callbacks. Unset => every callback is rejected (fail safe)."""
    return os.getenv("WEBHOOK_SECRET")
