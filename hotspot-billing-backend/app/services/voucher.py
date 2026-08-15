from datetime import datetime, timedelta
from secrets import choice

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_voucher_code(length: int = 8) -> str:
    return "".join(choice(ALPHABET) for _ in range(length))


def calculate_expiry(duration_hours: int) -> datetime:
    return datetime.utcnow() + timedelta(hours=duration_hours)
