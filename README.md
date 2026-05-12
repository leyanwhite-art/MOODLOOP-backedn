# MoodLoop API

A FastAPI backend for HR mental-health monitoring. Employees submit Arabic-language daily reflections, which are scrubbed of PII (spaCy multilingual NER + regex), classified by a 7-class AraBERT emotion model, and aggregated for HR into K-anonymized department dashboards and severity-graded alarms. An admin role manages users, departments, system settings, retention, and backups.

This project is the backend half of MoodLoop. The Next.js frontend lives in a sibling repository and talks to this API at `http://localhost:8000`.

---

## Table of contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Project layout](#project-layout)
- [Prerequisites](#prerequisites)
- [Configuration (`.env`)](#configuration-env)
- [Running with Docker (recommended)](#running-with-docker-recommended)
- [Running locally without Docker](#running-locally-without-docker)
- [Database migrations](#database-migrations)
- [Seeding development data](#seeding-development-data)
- [API overview](#api-overview)
- [Authentication](#authentication)
- [Background jobs](#background-jobs)
- [K-anonymity and privacy guarantees](#k-anonymity-and-privacy-guarantees)
- [Reflection text encryption](#reflection-text-encryption)
- [Troubleshooting](#troubleshooting)

---

## Features

- **Three roles**: `employee`, `hr`, `admin` — each with its own login route and access scope.
- **Arabic-only reflections**: server-side validates the Arabic Unicode range, length (100–1000 chars), max 3 per UTC day, and a 2-hour cooldown between submissions.
- **PII scrubbing**: PER / LOC / ORG / GPE entities replaced with `[REMOVED]`; digits, emails, phone numbers, and emojis stripped before storage.
- **AraBERT 7-class emotion classifier** (`predict.py`) over the cleaned text.
- **K-anonymized department alarms**: emitted only when ≥5 distinct employees reflected in the trailing 7-day window. Severity is graded `low / medium / high / critical` by the share of negative sentiment.
- **Critical-keyword alerts**: high-signal phrases trigger a separate HR-visible alert stream.
- **At-rest encryption** of reflection text via Fernet (key in `.env`, see below).
- **Email flows**: verification + password reset, with raw tokens emailed to the user and only their SHA-256 hashes stored server-side.
- **Audit log**: login attempts, password changes, admin actions, etc.
- **Scheduled jobs**: daily alarm recompute (12:00) and retention purge (03:00) via APScheduler.
- **Admin tooling**: user CRUD, department CRUD, system settings, activity logs, model info, CSV export, and `pg_dump` / `psql` backup/restore endpoints.

---

## Tech stack

- **FastAPI** 0.136 + Starlette + Uvicorn
- **SQLAlchemy** 2.0 + **PostgreSQL 15** + **Alembic** migrations
- **Pydantic v2** / `pydantic-settings`
- **python-jose** (JWT) + **passlib/bcrypt** (password hashing)
- **cryptography** (Fernet) for reflection encryption
- **fastapi-mail** for transactional email
- **APScheduler** for background jobs
- **spaCy** (`xx_ent_wiki_sm`) for NER-based PII scrubbing
- **transformers** + **torch** for the AraBERT 7-class emotion model

Python 3.11 is the targeted runtime (matches the Docker image).

---

## Project layout

```
MOODLOOP-backedn/
├── app/
│   ├── main.py              # FastAPI app, CORS, scheduler, exception handler, router wiring
│   ├── config.py            # pydantic-settings loaded from .env
│   ├── database.py          # SQLAlchemy engine/session + get_db dependency
│   ├── models.py            # ORM models + enums (Role, Sentiment, Emotion, Severity, ...)
│   ├── schemas.py           # Pydantic request/response models
│   ├── crud.py              # Reusable DB helpers
│   ├── routers/
│   │   ├── auth.py          # /auth/*           — register, login, verify-email, password flows
│   │   ├── users.py         # /users/*          — /me + HR list/get
│   │   ├── reflections.py   # /reflections/*    — submit, predict-only, history
│   │   ├── alarms.py        # /alarms/*         — HR alarm queries + manual trigger
│   │   ├── hr.py            # /api/hr/*         — dashboard stats, trends, profile, alerts
│   │   ├── admin.py         # /api/admin/*     — users, depts, settings, logs, backup/restore
│   │   └── employee.py      # NOT registered (broken legacy module — ignore)
│   └── utils/
│       ├── security.py      # bcrypt + JWT + SHA-256 token hashing
│       ├── crypto.py        # Fernet wrapper for reflection at-rest encryption
│       ├── alarm.py         # K-anonymized department alarm computation
│       ├── keyword_alarm.py # Critical-keyword detection
│       ├── text_cleaner.py  # spaCy + regex PII scrub
│       ├── email.py         # fastapi-mail wrapper, verification/reset links
│       ├── audit.py         # Activity log writer
│       └── settings_store.py# Runtime-mutable system settings backed by SystemSetting table
├── alembic/                 # Alembic env + versioned migrations
├── arabert_emotions_7class/ # Local AraBERT model directory (gitignored, see below)
├── predict.py               # Standalone model loader + classifier
├── seed.py                  # Dev fixture: HR + admin + 30 employees + reflections
├── test_model.py            # Smoke-test for predict.py
├── docker-compose.yml       # Postgres + API
├── Dockerfile               # Python 3.11 + postgresql-client + uvicorn
├── requirements.txt
└── .env.example
```

---

## Prerequisites

You will need either:

- **Docker + Docker Compose** (simplest path — Postgres comes with the stack), or
- **Python 3.11**, **PostgreSQL 15**, and the ability to install native deps for `psycopg2-binary`, `cryptography`, and `torch`.

You also need:

1. **An SMTP account** for `MAIL_*` (Gmail with an app password works out of the box). Without it, registration still succeeds, but verification/reset emails won't deliver.
2. **The AraBERT model directory** at `./arabert_emotions_7class/`. It is **not** in the repo (gitignored — large binary). Drop the fine-tuned HuggingFace model files there before starting anything that touches `predict.py`. If the directory is missing, the `/reflections/` endpoint and `/reflections/predict-only` will fail at request time, but the rest of the API still boots.

---

## Configuration (`.env`)

Copy the template and fill it in:

```bash
cp .env.example .env
```

Required keys (everything in `.env.example` is required at import time — `pydantic-settings` will crash on startup if any are missing):

| Key | Notes |
|---|---|
| `DATABASE_URL` | e.g. `postgresql://postgres:postgres@db:5432/moodloop_db` for Docker, or `...@localhost:5432/...` for local. |
| `SECRET_KEY` | JWT signing key. Generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"`. |
| `ALGORITHM` | `HS256`. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | e.g. `30`. |
| `MAIL_USERNAME` / `MAIL_PASSWORD` / `MAIL_FROM` | SMTP creds. For Gmail use an [app password](https://myaccount.google.com/apppasswords). |
| `MAIL_PORT` / `MAIL_SERVER` | `587` / `smtp.gmail.com` for Gmail. |
| `FRONTEND_URL` | Base URL the verification/reset emails link back to (e.g. `http://localhost:3000`). |
| `REFLECTION_ENC_KEY` | Fernet key for at-rest reflection encryption. Generate **once** and **do not lose it** — losing it makes existing reflections undecryptable: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |

---

## Running with Docker (recommended)

```bash
# 1. Configure
cp .env.example .env
# edit .env — at minimum set SECRET_KEY, REFLECTION_ENC_KEY, MAIL_* (for emails)

# 2. Drop the AraBERT model into ./arabert_emotions_7class/
#    (config.json, model.safetensors, tokenizer files, etc.)

# 3. Boot the stack
docker-compose up --build
```

This starts:

- `db` — Postgres 15 on `localhost:5432` (user/pass `postgres` / `postgres`, db `moodloop_db`).
- `api` — Uvicorn on `http://localhost:8000` with `--reload`, the source tree bind-mounted for live edits.

First boot only — run the migrations and (optionally) seed:

```bash
docker-compose exec api alembic upgrade head
docker-compose exec api python seed.py
```

Hit the OpenAPI docs at `http://localhost:8000/docs`.

---

## Running locally without Docker

```bash
# 1. System: install Python 3.11 and Postgres 15, then create the DB
createdb moodloop_db

# 2. Project: virtualenv + deps
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Point DATABASE_URL at your local Postgres (host=localhost, not db).

# 4. Drop the AraBERT model into ./arabert_emotions_7class/

# 5. Migrate
alembic upgrade head

# 6. (optional) Seed
python seed.py

# 7. Run
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000/docs` for the interactive Swagger UI.

> **Note**: an older quick-start guide mentioned `--port 8080`. Use **`8000`** — that is what `docker-compose.yml`, the Dockerfile's `EXPOSE`, and the frontend's `NEXT_PUBLIC_API_URL` all expect.

---

## Database migrations

Alembic reads the DB URL from `app/config.py` (i.e. `.env`) — `alembic.ini` has `sqlalchemy.url =` blank intentionally. `target_metadata` is `app.models.Base.metadata`, so autogenerate picks up model changes.

```bash
alembic upgrade head                       # apply all migrations
alembic revision --autogenerate -m "msg"   # generate a new migration from model diff
alembic downgrade -1                       # roll back one revision
alembic history                            # list revisions
```

Existing revisions cover initial schema, the `cleaned_text` column, department name widening, the `selected_emotion` field, admin role + `is_active`, system settings + activity logs, reflection encryption, and critical-keyword alerts.

---

## Seeding development data

```bash
python seed.py
```

This creates:

- Departments (Accounting, Maintenance, Human Resources, …).
- **HR account** — `hr@moodloop.com` / `Hr@123456`
- **Admin account** — `admin@moodloop.com` / `Admin@123456`
- **30 employees** — all `*@moodloop.com` / `Employee@123`
- A scatter of reflections + (randomly generated) sentiment rows so HR dashboards have something to draw.

Re-running the seed is idempotent for accounts (it checks before inserting).

---

## API overview

The OpenAPI spec at `/docs` is the authoritative reference. High-level map:

### `/auth/*` — registration, login, password flows
- `POST /auth/register` — employee self-registration (emails a verification token).
- `POST /auth/hr/register` — HR registration.
- `GET  /auth/verify-email?token=...`
- `POST /auth/login` — employee login → JWT.
- `POST /auth/hr/login` — HR login → JWT.
- `POST /auth/admin/login` — admin login → JWT.
- `POST /auth/forgot-password` — generic response, prevents email enumeration.
- `POST /auth/reset-password?token=...&new_password=...`
- `POST /auth/change-password` (authenticated).

### `/users/*`
- `GET /users/me` — current user.
- `GET /users/` (HR) — list employees.
- `GET /users/{employee_id}` (HR).

### `/reflections/*`
- `POST /reflections/` — submit a reflection (Arabic, 100–1000 chars, ≤3/day, 2h cooldown).
- `POST /reflections/predict-only` — debug endpoint for the model; returns the prediction without writing a row.
- `GET  /reflections/my` — caller's own reflections.

### `/alarms/*` (HR only)
- `GET  /alarms/` — all current department alarms.
- `GET  /alarms/severity/{severity}` — filter by severity.
- `GET  /alarms/department/{department_id}` — single department.
- `POST /alarms/trigger` — recompute alarms now (the scheduler also does this daily).

### `/api/hr/*` (HR dashboard)
- `GET /api/hr/stats` — top-level dashboard numbers.
- `GET /api/hr/departments` — per-department breakdown.
- `GET /api/hr/monthly-trends`, `/api/hr/yearly-trends`, `/api/hr/mood-distribution`.
- `GET /api/hr/critical-alerts`, `POST /api/hr/critical-alerts/{id}/resolve`.
- `GET /api/hr/total-employees`, `/api/hr/messages`.
- `GET|PUT /api/hr/profile`.

### `/api/admin/*` (admin only)
- Users: `GET /users`, `POST /users`, `PATCH /users/{id}`, `POST /users/{id}/deactivate`, `POST /users/{id}/reactivate`.
- Departments: `GET|POST|PATCH|DELETE /departments[/{id}]`.
- Settings: `GET /settings`, `PUT /settings/{key}`.
- Operations: `GET /system/health`, `GET /activity-logs`, `GET|POST /model`, `GET /messages.csv`, `POST /backup`, `POST /restore`.

---

## Authentication

JWT bearer tokens via `python-jose` over `Authorization: Bearer <token>`.

- Payload: `sub` = stringified `employee_id`, `role` = `"employee" | "hr" | "admin"`.
- Default lifetime: `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30).
- Role enforcement lives in two helpers — `app/routers/users.py::hr_only` (used by `users`, `reflections`, `alarms`) and `app/routers/hr.py::get_current_hr` (used only by `/api/hr/*`). Admin gates use `get_current_admin` in `admin.py`.
- Email-verification and password-reset tokens are 256-bit random strings (`secrets.token_urlsafe(32)`); only their **SHA-256 hash** is stored — the raw value is emailed to the user and the inbound token is hashed and compared on callback. Reset tokens expire after 1 hour.

---

## Background jobs

`app/main.py` starts an APScheduler `BackgroundScheduler` at app lifespan:

| Job | Schedule (server local time) | What it does |
|---|---|---|
| `daily_alarm_check` | 12:00 daily | Recomputes per-department alarms over the trailing 7 days. |
| `daily_retention` | 03:00 daily | Purges reflections older than the configured retention window (`SystemSetting`). |

You can also trigger an alarm recompute on demand via `POST /alarms/trigger`.

---

## K-anonymity and privacy guarantees

`app/utils/alarm.py::calculate_department_alarm` will **not** emit an alarm unless **≥5 distinct employees** reflected in the trailing 7-day window. This is a hard floor and should not be lowered without an explicit policy decision — it is the only thing preventing a small department from being uniquely identifiable from negative-sentiment counts.

Severity bands (share of negative sentiment in the window):

| Negative ratio | Severity |
|---|---|
| < 0.30 | no alarm |
| 0.30 – 0.49 | `low` |
| 0.50 – 0.64 | `medium` |
| 0.65 – 0.79 | `high` |
| ≥ 0.80 | `critical` |

Each department has at most one active alarm row at any time — recompute deletes the old row before writing the new one.

PII is scrubbed before storage: `app/utils/text_cleaner.py` runs spaCy NER over the Arabic text and replaces `PER / LOC / ORG / GPE` spans with `[REMOVED]`, then strips digits, emails, phone numbers, and emojis. The cleaned text is what gets stored in `cleaned_text`. The **raw** reflection text is also stored — but encrypted at rest (next section).

---

## Reflection text encryption

`app/utils/crypto.py` wraps `cryptography.fernet.Fernet`. The Fernet key in `REFLECTION_ENC_KEY` is used to encrypt the raw reflection text column. Migration `f1d92a44c810` introduces the encrypted storage.

**If you lose `REFLECTION_ENC_KEY`, all existing reflection text becomes unrecoverable.** Treat it the same as `SECRET_KEY` — generate once, store securely, and back it up alongside the database.

---

## Troubleshooting

**`pydantic_settings.exceptions.SettingsError: ... validation errors`** at startup — a key in `.env.example` is missing or empty in `.env`. Every listed field is required at import time.

**`OSError: ... model files not found`** when calling `/reflections/` — `./arabert_emotions_7class/` is missing or incomplete. Drop the model files in or skip endpoints that hit the model.

**CORS errors from the frontend** — `app/main.py` allow-lists `localhost:3000`, `localhost:5173`, and their `127.0.0.1` equivalents. If the frontend dev server runs on something else, add it to the `allow_origins` list.

**`alembic` can't find the DB** — `alembic.ini` is intentionally blank for `sqlalchemy.url`. The URL comes from `.env` via `app/config.py`. If you ran `alembic` before creating `.env`, you'll get a confusing connection error.

**Email never arrives** — Gmail requires an [app password](https://myaccount.google.com/apppasswords), not your account password, and 2FA must be enabled to create one. Check the API logs for `Failed to send ... email` — `forgot-password` swallows mailer errors so the response stays generic to prevent enumeration.

**`docker-compose exec api alembic upgrade head` fails with `connection refused`** — Postgres may still be initializing on first boot. Wait a few seconds and retry, or `docker-compose logs db` to confirm it's ready.
