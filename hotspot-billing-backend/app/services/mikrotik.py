from __future__ import annotations

from datetime import datetime

from librouteros import connect

from app.config import settings


def get_connection():
    if not settings.mikrotik_host:
        raise RuntimeError("MIKROTIK_HOST is not configured. Add the hAP lite address to backend/.env.")
    try:
        # librouteros uses the unencrypted API by default. TLS, when needed,
        # is configured with ``ssl_wrapper`` rather than a ``use_ssl`` flag.
        return connect(
            host=settings.mikrotik_host,
            port=settings.mikrotik_port,
            username=settings.mikrotik_user,
            password=settings.mikrotik_password,
        )
    except Exception as exc:
        raise RuntimeError(f"Cannot reach MikroTik hAP lite at {settings.mikrotik_host}: {exc}") from exc


def create_hotspot_user(username: str, password: str, profile_name: str, comment: str) -> None:
    api = get_connection()
    try:
        api.path("ip", "hotspot", "user").add(name=username, password=password, profile=profile_name, comment=comment)
    finally:
        api.close()


def disable_hotspot_user(username: str) -> None:
    api = get_connection()
    try:
        users = list(api.path("ip", "hotspot", "user").select(".id").where(name=username))
        for user in users:
            api.path("ip", "hotspot", "user").update(**{".id": user[".id"], "disabled": "yes"})
    finally:
        api.close()


def remove_active_session(username: str) -> None:
    api = get_connection()
    try:
        sessions = list(api.path("ip", "hotspot", "active").select(".id").where(user=username))
        for session in sessions:
            api.path("ip", "hotspot", "active").remove(session[".id"])
    finally:
        api.close()


def list_expired_users() -> list[str]:
    """Return hotspot users whose ISO-8601 expiry comment has passed."""
    api = get_connection()
    try:
        users = api.path("ip", "hotspot", "user").select("name", "comment")
        now = datetime.utcnow()
        expired = []
        for user in users:
            try:
                if user.get("comment", "").startswith("expires=") and datetime.fromisoformat(user["comment"].split("=", 1)[1]) < now:
                    expired.append(user["name"])
            except ValueError:
                continue
        return expired
    finally:
        api.close()
