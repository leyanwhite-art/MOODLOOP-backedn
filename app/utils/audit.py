"""Activity-log writer. Keeps the meta payload free of reflection text and
per-employee mood data so the log itself can't become a privacy leak."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app import models


# Fields banned from `meta` — defence-in-depth against accidental PII leaks.
_BANNED_META_KEYS = {
    "input_text", "cleaned_text", "reflection", "reflections",
    "sentiment", "emotion", "wellness_tip", "password", "password_hash",
}


def _scrub_meta(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    if not meta:
        return meta
    return {k: v for k, v in meta.items() if k not in _BANNED_META_KEYS}


def log_action(
    db: Session,
    request: Request | None,
    actor: models.Employee | None,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    meta: dict[str, Any] | None = None,
) -> models.ActivityLog:
    actor_id = actor.employee_id if actor else None
    actor_role = None
    if actor and actor.role is not None:
        actor_role = actor.role.value if hasattr(actor.role, "value") else str(actor.role)

    ip = None
    user_agent = None
    if request is not None:
        if request.client:
            ip = request.client.host
        user_agent = request.headers.get("user-agent")

    entry = models.ActivityLog(
        actor_employee_id=actor_id,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        meta=_scrub_meta(meta),
        ip=ip,
        user_agent=user_agent,
    )
    db.add(entry)
    db.commit()
    return entry
