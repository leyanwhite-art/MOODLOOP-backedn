"""Runtime-tunable system settings backed by the system_settings table.

Why this exists: alarm thresholds, the K-anonymity floor, retention TTL,
and reflection rate limits used to be hardcoded. The admin dashboard
needs to change them without a deploy. Read paths go through `get_setting`
(small in-process cache, ~60s TTL). Write paths go through `set_setting`
which validates against the schema and logs to activity_logs.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app import models


# ── Setting schema ─────────────────────────────────────────────────────
# `min`/`max` bound numeric values; admins can never push past these.
# `floor`-only fields (k_anon) are clamped *up* even if the request is lower.
SETTING_SCHEMA: dict[str, dict[str, Any]] = {
    "alarm_threshold_low": {
        "type": "float", "default": 0.30, "min": 0.0, "max": 1.0,
        "description": "Negative-ratio cutoff for a 'low' severity alarm.",
    },
    "alarm_threshold_medium": {
        "type": "float", "default": 0.50, "min": 0.0, "max": 1.0,
        "description": "Negative-ratio cutoff for a 'medium' severity alarm.",
    },
    "alarm_threshold_high": {
        "type": "float", "default": 0.65, "min": 0.0, "max": 1.0,
        "description": "Negative-ratio cutoff for a 'high' severity alarm.",
    },
    "alarm_threshold_critical": {
        "type": "float", "default": 0.80, "min": 0.0, "max": 1.0,
        "description": "Negative-ratio cutoff for a 'critical' severity alarm.",
    },
    "alarm_k_anonymity_floor": {
        # Hard floor of 5 — admins may raise but never lower this.
        "type": "int", "default": 5, "min": 5, "max": 100, "floor": 5,
        "description": "Minimum distinct employees required to emit a department alarm.",
    },
    "reflection_retention_days": {
        "type": "int", "default": 365, "min": 30, "max": 3650,
        "description": "Reflections (and their sentiment rows) are purged after this many days.",
    },
    "max_reflections_per_day": {
        "type": "int", "default": 3, "min": 1, "max": 20,
        "description": "Per-employee daily reflection cap.",
    },
    "reflection_cooldown_hours": {
        "type": "int", "default": 2, "min": 0, "max": 24,
        "description": "Hours an employee must wait between reflection submissions.",
    },
    "model_hub_id": {
        "type": "string", "default": "ghaida75/arabert-emotions-7class",
        "description": "HuggingFace Hub model ID used by predict.py.",
    },
}


# ── In-process cache ───────────────────────────────────────────────────
_CACHE_TTL_SECONDS = 60.0
_cache: dict[str, tuple[float, Any]] = {}


def invalidate_cache(key: str | None = None) -> None:
    if key is None:
        _cache.clear()
    else:
        _cache.pop(key, None)


def get_setting(db: Session, key: str) -> Any:
    if key not in SETTING_SCHEMA:
        raise KeyError(f"Unknown setting: {key}")

    now = time.monotonic()
    cached = _cache.get(key)
    if cached is not None and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    value = row.value if row is not None else SETTING_SCHEMA[key]["default"]
    _cache[key] = (now, value)
    return value


def get_all_settings(db: Session) -> list[dict[str, Any]]:
    rows = {r.key: r for r in db.query(models.SystemSetting).all()}
    out: list[dict[str, Any]] = []
    for key, schema in SETTING_SCHEMA.items():
        row = rows.get(key)
        out.append({
            "key": key,
            "value": row.value if row is not None else schema["default"],
            "type": schema["type"],
            "min": schema.get("min"),
            "max": schema.get("max"),
            "default": schema["default"],
            "description": schema.get("description"),
            "updated_at": row.updated_at if row is not None else None,
        })
    return out


class SettingValidationError(ValueError):
    pass


def _coerce_and_validate(key: str, value: Any) -> Any:
    schema = SETTING_SCHEMA[key]
    t = schema["type"]
    if t == "float":
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise SettingValidationError(f"{key} must be a number")
    elif t == "int":
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise SettingValidationError(f"{key} must be an integer")
    elif t == "bool":
        if not isinstance(value, bool):
            raise SettingValidationError(f"{key} must be a boolean")
    elif t == "string":
        if not isinstance(value, str) or not value.strip():
            raise SettingValidationError(f"{key} must be a non-empty string")

    if "min" in schema and value < schema["min"]:
        value = schema["min"]
    if "max" in schema and value > schema["max"]:
        value = schema["max"]
    # Explicit hard floor for the K-anonymity setting — admins can raise it
    # past the schema min but can never lower it past `floor`.
    floor = schema.get("floor")
    if floor is not None and value < floor:
        value = floor
    return value


def set_setting(db: Session, key: str, raw_value: Any, actor_id: int | None) -> tuple[Any, bool]:
    """Validate, persist, and audit. Returns (stored_value, was_clamped)."""
    if key not in SETTING_SCHEMA:
        raise KeyError(f"Unknown setting: {key}")
    coerced = _coerce_and_validate(key, raw_value)
    was_clamped = coerced != raw_value and not (
        # int vs float comparisons after coercion shouldn't count as clamping
        SETTING_SCHEMA[key]["type"] in {"int", "float"}
        and isinstance(raw_value, (int, float))
        and float(coerced) == float(raw_value)
    )

    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    if row is None:
        row = models.SystemSetting(key=key, value=coerced, updated_by=actor_id)
        db.add(row)
    else:
        row.value = coerced
        row.updated_by = actor_id
    db.commit()
    invalidate_cache(key)
    return coerced, was_clamped
