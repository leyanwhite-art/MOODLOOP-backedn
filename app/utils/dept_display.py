"""Shared department name display helper.

Normalizes the enum-or-string department name and applies the human-readable
mapping (e.g. "Human Resources" → "HR") used in HR-facing responses.
Previously lived inline in app/routers/hr.py — extracted so other routers
(notably alarms.py) can render department names with the same rules.
"""

from app.models import Department


_DEPT_DISPLAY = {
    "Human Resources": "HR",
}


def dept_display(dept: Department | None) -> str | None:
    if dept is None:
        return None
    raw = dept.name.value if hasattr(dept.name, "value") else dept.name
    return _DEPT_DISPLAY.get(raw, raw)
