# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

MoodLoop API — a FastAPI service for HR mental-health monitoring. Employees submit Arabic-language daily reflections, which are cleaned (spaCy multilingual NER + regex) and classified by an AraBERT 7-class emotion model (`predict.py`). HR users see aggregated, K-anonymized department dashboards and severity-based alarms.

## Commands

The repo has no `pytest`/lint config, no `Makefile`, and no package script entries. Run everything by hand.

```bash
# Local run (expects a running Postgres reachable via $DATABASE_URL)
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# Full stack (Postgres + API with hot reload)
docker-compose up --build

# Alembic migrations (DATABASE_URL is read from app/config.py → .env, NOT alembic.ini)
alembic upgrade head
alembic revision --autogenerate -m "describe change"
alembic downgrade -1

# Seed dev data (departments, HR account, 30 employees, reflections, sentiments)
# Login after seeding: hr@moodloop.com / Hr@123456   |   *@moodloop.com / Employee@123
python seed.py

# Smoke-test the ML model in isolation (needs ./arabert_emotions_7class/ on disk — gitignored)
python test_model.py
```

`tests/test_users.py` exists but is empty; there is no test suite to run yet.

## Architecture

### Request flow & router layout
`app/main.py` boots FastAPI, mounts CORS (hardcoded to `localhost:5173` / `127.0.0.1:5173`), installs a global exception middleware that logs tracebacks server-side and returns generic 500s, and registers an APScheduler `BackgroundScheduler` that runs `run_daily_alarm_check` every day at 12:00 (server local time).

Mounted routers and their prefixes (note the inconsistency):
- `auth` → `/auth/*` — register, login, verify-email, forgot/reset/change-password (separate flows for employee vs HR)
- `users` → `/users/*` — `/me` for anyone, list/get employee for HR only
- `reflections` → `/reflections/*` — employee submission + history
- `alarms` → `/alarms/*` — HR-only alarm queries + manual trigger
- `hr` → `/api/hr/*` — HR dashboard endpoints (stats, departments, monthly/yearly trends, mood distribution, messages, profile)

`app/routers/employee.py` is **not** registered in `main.py` and is broken (bare `from database import …` instead of `from app.database`, references `EmotionHistory` schema that doesn't exist). A recent commit removed a similar unused/broken router; treat this file the same way — don't import from it, and consider proposing its removal rather than fixing it piecemeal.

### Auth & role enforcement
JWT bearer tokens via `python-jose` + `HTTPBearer`. Payload: `sub` = `str(employee_id)`, `role` = role string. Two parallel patterns exist for HR gating — keep them in sync if you change either:
- `app/routers/users.py::hr_only` — checks `current_user.role != "hr"`, used by `users`, `reflections`, `alarms`.
- `app/routers/hr.py::get_current_hr` — re-decodes the token, checks `role` claim, then re-loads the employee. Used only by `/api/hr/*`.

`Employee` is the single user table; HR users have `role=hr` and `department_id=None`.

### Tokens (verification / password reset)
Generated with `secrets.token_urlsafe(32)`, but **only the SHA-256 hash is stored** in `verification_token` / `reset_token`. The raw token is emailed to the user; on callback the handler hashes the inbound token and matches against the stored hash (`app/utils/security.py::hash_token`, used in `auth.py`). Don't store raw tokens. SHA-256 (not bcrypt) is intentional here because the input already has 256 bits of entropy.

### Reflections pipeline
`POST /reflections/` enforces, in order: role ≠ HR → `validate_arabic_text` (regex for U+0600–U+06FF) → length 100–1000 chars → ≤3 reflections per UTC day → ≥2 hours since last reflection. Then `clean_arabic_text` (spaCy `xx_ent_wiki_sm`) replaces PER/LOC/ORG/GPE entities with `[REMOVED]` and strips digits/emails/phones/emojis before storing.

The AraBERT model in `predict.py` is **not yet wired into the live `/reflections/` endpoint** — sentiment rows are only produced by `seed.py` (random) and by the broken `employee.py` router. If you're connecting prediction into the real flow, do it inside `app/routers/reflections.py` and write a `SentimentAnalysis` row alongside the `DailyReflection`. `predict.py` has its own Arabic normalization (`predict.py::clean_arabic_text`) tuned for the model — don't replace it with the spaCy-based `app/utils/text_cleaner.py`, which is for PII scrubbing of stored text.

### Alarms (K-anonymity)
`app/utils/alarm.py::calculate_department_alarm` aggregates sentiment over the last 7 days per department. It **refuses to emit an alarm unless ≥5 distinct employees reflected in the window** (K-anonymity floor — do not lower this). Severity thresholds on negative ratio: 0.30 low, 0.50 medium, 0.65 high, 0.80 critical; below 0.30 returns `None`. Existing alarms for a department are deleted before a new one is written, so there's at most one row per department.

### Datetime convention
All DB datetime columns are **naive**; all code writes naive UTC via `datetime.now(timezone.utc).replace(tzinfo=None)` (or `models.utcnow_naive()` for column defaults). Mixing tz-aware values into these columns will break comparisons. Keep new code on the same convention.

### Migrations
Alembic reads the DB URL from `app/config.py` (i.e. `.env`) in `alembic/env.py` — `alembic.ini` has `sqlalchemy.url =` blank intentionally. `target_metadata` is `app.models.Base.metadata`, so autogenerate picks up model changes. The `cleaned_text` column on `daily_reflections` was added in the second migration; new SQLAlchemy fields need a corresponding revision.

### Settings
`pydantic-settings` loads from `.env` (see `.env.example`). All listed fields are required at import time — adding a setting without a default will crash the app on startup until `.env` is updated. `FRONTEND_URL` is used to build verification and password-reset links in `app/utils/email.py`.

### Things that are gitignored but required at runtime
- `.env` — all of `DATABASE_URL`, `SECRET_KEY`, `MAIL_*`, `FRONTEND_URL`.
- `arabert_emotions_7class/` — the fine-tuned HuggingFace model directory loaded by `predict.py`. Not in the repo; obtain separately before running anything that imports `predict`.
