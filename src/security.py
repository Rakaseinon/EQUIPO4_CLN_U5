from datetime import datetime, timedelta, timezone


def can_cancel(status, owner_id, user_id, is_admin, created_at, now=None):
    now = now or datetime.now(timezone.utc)
    if status == "SHIPPED":
        return False
    if is_admin:
        return True
    return owner_id == user_id and now - created_at < timedelta(hours=24)
