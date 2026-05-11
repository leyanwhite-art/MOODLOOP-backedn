# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

MoodLoop API — a FastAPI service for HR mental-health monitoring. Employees submit Arabic-language daily reflections, which are cleaned (spaCy multilingual NER + regex), encrypted at rest, and classified by an AraBERT 7-class emotion model (`predict.py`). HR users see aggregated, K-anonymized department dashboards plus severity-graded department alarms and critical-keyword alerts. An admin role manages users, departments, system settings, retention, and DB backup/restore.

`README.md` documents end-user setup and the public API surface; this file is the operator-facing map for changing the code. Don't duplicate the README here.

## Commands

The repo has no `pytest`/lint config, no `Makefile`, and no package script entries. Run everything by hand.

```bash
# Local run (expects a running Postgres reachable via $DATABASE_URL).
# Use port 8000 — docker-compose, the Dockerfile EXPOSE, and the Next.js frontend
# (NEXT_PUBLIC_API_URL) all expect :8000.
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Full stack (Postgres + API with hot reload)
docker-compose up --build

# Alembic migrations (DATABASE_URL is read from app/config.py → .env, NOT alembic.ini)
alembic upgrade head
alembic revision --autogenerate -m "describe change"
alembic downgrade -1

# Seed dev data (departments, HR + admin accounts, 30 employees, reflections, sentiments)
# Login after seeding:
#   hr@moodloop.com    / Hr@123456
#   admin@moodloop.com / Admin@123456
#   *@moodloop.com     / Employee@123
python seed.py

# Smoke-test the ML model in isolation (needs ./arabert_emotions_7class/ on disk — gitignored)
python test_model.py
```

`tests/test_users.py` exists but is empty; there is no test suite to run yet.

## Architecture

### Request flow & router layout
`app/main.py` boots FastAPI, mounts CORS (`localhost:5173` / `127.0.0.1:5173` for the Vite default and `localhost:3000` / `127.0.0.1:3000` for the Next.js frontend), installs a global exception **handler** (registered as `@app.exception_handler(Exception)`, not as HTTP middleware — that placement is intentional so CORS headers still attach to 500s), and registers an APScheduler `BackgroundScheduler` with two daily jobs: `daily_alarm_check` at 12:00 and `daily_retention` at 03:00 (server local time).

Mounted routers and their prefixes (note the inconsistency):
- `auth` → `/auth/*` — register, login, verify-email, forgot/reset/change-password (separate flows for employee / HR / admin)
- `users` → `/users/*` — `/me` for anyone, list/get employee for HR only
- `reflections` → `/reflections/*` — employee submission, history, and a `/predict-only` debug endpoint
- `alarms` → `/alarms/*` — HR-only alarm queries + manual trigger
- `hr` → `/api/hr/*` — HR dashboard endpoints (stats, departments, monthly/yearly trends, mood distribution, critical alerts, messages, profile)
- `admin` → `/api/admin/*` — admin-only user/department CRUD, system settings, activity logs, model info, CSV export, pg_dump/psql backup & restore

`app/routers/employee.py` is **not** registered in `main.py` and is broken (bare `from database import …` instead of `from app.database`, references `EmotionHistory` schema that doesn't exist). A recent commit removed a similar unused/broken router; treat this file the same way — don't import from it, and consider proposing its removal rather than fixing it piecemeal.

### Auth & role enforcement
JWT bearer tokens via `python-jose` + `HTTPBearer`. Payload: `sub` = `str(employee_id)`, `role` ∈ `{"employee", "hr", "admin"}`. Three parallel role-gating patterns exist — keep them in sync if you change one:
- `app/routers/users.py::hr_only` — checks `current_user.role != "hr"`, used by `users`, `reflections`, `alarms`.
- `app/routers/hr.py::get_current_hr` — re-decodes the token, checks `role` claim, then re-loads the employee. Used only by `/api/hr/*`.
- `app/routers/admin.py::get_current_admin` — same shape as `get_current_hr` but for `role == "admin"`. Used only by `/api/admin/*`.

`Employee` is the single user table for all three roles. HR and admin rows have `department_id=None`. Admin separation also rides on `is_active` (deactivation flow exposes the user without deleting them).

### Tokens (verification / password reset)
Generated with `secrets.token_urlsafe(32)`, but **only the SHA-256 hash is stored** in `verification_token` / `reset_token`. The raw token is emailed to the user; on callback the handler hashes the inbound token and matches against the stored hash (`app/utils/security.py::hash_token`, used in `auth.py`). Don't store raw tokens. SHA-256 (not bcrypt) is intentional here because the input already has 256 bits of entropy.

### Reflections pipeline
`POST /reflections/` enforces, in order: role must be `employee` (HR and admin are rejected) → `validate_arabic_text` (regex for U+0600–U+06FF) → length 100–1000 chars → at most `max_reflections_per_day` per UTC day → at least `reflection_cooldown_hours` since the last reflection. The per-day cap and cooldown are **runtime-mutable system settings** (`app/utils/settings_store.py`, defaults 3 and 2 — admin can change them via `/api/admin/settings`); don't hardcode these limits in new code, read them through `get_setting(db, ...)`.

After validation, `app/utils/text_cleaner.py::clean_arabic_text` (spaCy `xx_ent_wiki_sm`) scrubs PII — PER/LOC/ORG/GPE entities → `[REMOVED]`, digits/emails/phones/emojis stripped — into `cleaned_text`. The model runs on the **plaintext raw input** (not the cleaned text) via `asyncio.to_thread(predict_emotion, ...)` from `predict.py`; the resulting emotion is mapped to a `SentimentEnum` via the `EMOTION_TO_SENTIMENT` table at the top of `app/routers/reflections.py` and a `SentimentAnalysis` row is written alongside the `DailyReflection`. The plaintext is then Fernet-encrypted (see *Reflection encryption*) before persisting to `input_text`. `predict.py` has its own Arabic normalization (`predict.py::clean_arabic_text`) tuned for the model — don't replace it with the spaCy-based PII scrubber.

Plaintext is also fed to `app/utils/keyword_alarm.py::detect_keywords`, which matches a curated list of high-severity Arabic phrases and writes `CriticalKeywordAlert` rows (surfaced to HR at `/api/hr/critical-alerts`).

### Alarms (K-anonymity)
`app/utils/alarm.py::calculate_department_alarm` aggregates sentiment over the last 7 days per department. It **refuses to emit an alarm unless ≥5 distinct employees reflected in the window** (K-anonymity floor — do not lower this). Severity thresholds on negative ratio: 0.30 low, 0.50 medium, 0.65 high, 0.80 critical; below 0.30 returns `None`. Existing alarms for a department are deleted before a new one is written, so there's at most one row per department.

Critical-keyword alerts (`CriticalKeywordAlert`) are a *separate* signal from department alarms — they fire per-reflection with no K-anonymity floor because they target acute individual risk, not aggregate mood. Don't conflate the two when reading the HR endpoints.

### Reflection encryption (at rest)
`app/utils/crypto.py` wraps `cryptography.fernet.Fernet` (key from `REFLECTION_ENC_KEY` in `.env`). `DailyReflection.input_text` is encrypted at write; reads decrypt via `_safe_decrypt` in `app/routers/reflections.py`, which falls back to passing the value through unchanged if it doesn't look like a Fernet token (so pre-migration rows still load). The `cleaned_text` column stays plaintext because it is already PII-scrubbed and is what the dashboards aggregate over.

Losing `REFLECTION_ENC_KEY` permanently destroys access to existing reflection plaintext. Generate once, back up alongside `SECRET_KEY`. Migration `f1d92a44c810` introduces the encrypted column.

### Audit log
`app/utils/audit.py::log_action(db, request, actor, action, target_type=..., target_id=..., meta=...)` writes `ActivityLog` rows. It auto-scrubs the `meta` dict before write. Wire it into auth events, admin actions, and any state-changing endpoint that an admin might later need to review; don't roll a parallel logger.

### System settings
`app/utils/settings_store.py` reads and writes `SystemSetting` rows with an in-process cache. `get_setting(db, key)` is the only correct accessor — it handles defaults, type coercion, and cache priming. `set_setting` validates against `_coerce_and_validate` and invalidates the cache. Admin exposes these via `GET/PUT /api/admin/settings[/{key}]`. Known keys currently include `max_reflections_per_day` and `reflection_cooldown_hours`; add new ones by extending the validator.

### Datetime convention
All DB datetime columns are **naive**; all code writes naive UTC via `datetime.now(timezone.utc).replace(tzinfo=None)` (or `models.utcnow_naive()` for column defaults). Mixing tz-aware values into these columns will break comparisons. Keep new code on the same convention.

### Migrations
Alembic reads the DB URL from `app/config.py` (i.e. `.env`) in `alembic/env.py` — `alembic.ini` has `sqlalchemy.url =` blank intentionally. `target_metadata` is `app.models.Base.metadata`, so autogenerate picks up model changes. The `cleaned_text` column on `daily_reflections` was added in the second migration; new SQLAlchemy fields need a corresponding revision.

### Environment config (`app/config.py`)
`pydantic-settings` loads from `.env` (see `.env.example`). All listed fields are required at import time — adding a setting without a default will crash the app on startup until `.env` is updated. `FRONTEND_URL` is used to build verification and password-reset links in `app/utils/email.py`. `REFLECTION_ENC_KEY` is the Fernet key consumed by `app/utils/crypto.py`. Distinguish this *static* env-loaded config from the *dynamic* `SystemSetting` table read via `settings_store` — env config requires a process restart, settings_store keys are hot-mutable from the admin panel.

### Things that are gitignored but required at runtime
- `.env` — all of `DATABASE_URL`, `SECRET_KEY`, `MAIL_*`, `FRONTEND_URL`, `REFLECTION_ENC_KEY`.
- `arabert_emotions_7class/` — the fine-tuned HuggingFace model directory loaded by `predict.py`. Not in the repo; obtain separately before running anything that imports `predict` (the `/reflections/` endpoint will fail at request time without it, but the rest of the API still boots).
