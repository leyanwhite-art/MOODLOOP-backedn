"""encrypt existing reflection input_text/cleaned_text and snippet rows

Revision ID: f1d92a44c810
Revises: e7a2c91f5b08
Create Date: 2026-05-12 01:20:00.000000

Re-encrypts every existing row using REFLECTION_ENC_KEY from the env. Aborts
loudly if the key is missing rather than silently corrupting data. Detects
already-encrypted rows (Fernet tokens start with 'gAAAAA') and skips them so
the migration is idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1d92a44c810"
down_revision: Union[str, None] = "e7a2c91f5b08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _looks_encrypted(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith("gAAAAA")


def _get_cipher():
    # Import lazily so alembic offline mode that doesn't need crypto still works
    # for inspecting the migration.
    from cryptography.fernet import Fernet
    from app.config import settings
    key = (settings.REFLECTION_ENC_KEY or "").strip()
    if not key:
        raise RuntimeError(
            "REFLECTION_ENC_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"` "
            "and add it to .env before running this migration."
        )
    return Fernet(key.encode("utf-8"))


def upgrade() -> None:
    cipher = _get_cipher()
    bind = op.get_bind()

    # daily_reflections: input_text + cleaned_text
    rows = bind.execute(sa.text(
        "SELECT reflection_id, input_text, cleaned_text FROM daily_reflections"
    )).fetchall()
    for r in rows:
        rid = r[0]
        raw, cleaned = r[1], r[2]
        new_raw = raw
        new_cleaned = cleaned
        if raw is not None and not _looks_encrypted(raw):
            new_raw = cipher.encrypt(raw.encode("utf-8")).decode("utf-8")
        if cleaned is not None and not _looks_encrypted(cleaned):
            new_cleaned = cipher.encrypt(cleaned.encode("utf-8")).decode("utf-8")
        if new_raw is not raw or new_cleaned is not cleaned:
            bind.execute(
                sa.text(
                    "UPDATE daily_reflections SET input_text = :raw, cleaned_text = :cleaned "
                    "WHERE reflection_id = :rid"
                ),
                {"raw": new_raw, "cleaned": new_cleaned, "rid": rid},
            )

    # critical_keyword_alerts.snippet
    alerts = bind.execute(sa.text(
        "SELECT alert_id, snippet FROM critical_keyword_alerts"
    )).fetchall()
    for a in alerts:
        aid, snippet = a[0], a[1]
        if snippet is not None and not _looks_encrypted(snippet):
            new = cipher.encrypt(snippet.encode("utf-8")).decode("utf-8")
            bind.execute(
                sa.text("UPDATE critical_keyword_alerts SET snippet = :s WHERE alert_id = :aid"),
                {"s": new, "aid": aid},
            )


def downgrade() -> None:
    from cryptography.fernet import InvalidToken
    cipher = _get_cipher()
    bind = op.get_bind()

    rows = bind.execute(sa.text(
        "SELECT reflection_id, input_text, cleaned_text FROM daily_reflections"
    )).fetchall()
    for r in rows:
        rid, raw, cleaned = r[0], r[1], r[2]
        new_raw = raw
        new_cleaned = cleaned
        try:
            if raw is not None and _looks_encrypted(raw):
                new_raw = cipher.decrypt(raw.encode("utf-8")).decode("utf-8")
            if cleaned is not None and _looks_encrypted(cleaned):
                new_cleaned = cipher.decrypt(cleaned.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            raise RuntimeError(
                f"Cannot decrypt reflection_id={rid} — REFLECTION_ENC_KEY does not match the row's key."
            )
        if new_raw is not raw or new_cleaned is not cleaned:
            bind.execute(
                sa.text(
                    "UPDATE daily_reflections SET input_text = :raw, cleaned_text = :cleaned "
                    "WHERE reflection_id = :rid"
                ),
                {"raw": new_raw, "cleaned": new_cleaned, "rid": rid},
            )

    alerts = bind.execute(sa.text(
        "SELECT alert_id, snippet FROM critical_keyword_alerts"
    )).fetchall()
    for a in alerts:
        aid, snippet = a[0], a[1]
        try:
            if snippet is not None and _looks_encrypted(snippet):
                new = cipher.decrypt(snippet.encode("utf-8")).decode("utf-8")
                bind.execute(
                    sa.text("UPDATE critical_keyword_alerts SET snippet = :s WHERE alert_id = :aid"),
                    {"s": new, "aid": aid},
                )
        except InvalidToken:
            raise RuntimeError(
                f"Cannot decrypt critical_keyword_alert id={aid} — key mismatch."
            )
