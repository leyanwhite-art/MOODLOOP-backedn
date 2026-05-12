"""Admin router. All endpoints under /api/admin/*.

Privacy boundary:
- No endpoint may return DECRYPTED reflection text. The `encrypted_message`
  column exported by /messages.csv is the raw Fernet ciphertext from
  `daily_reflections.input_text` — opaque without REFLECTION_ENC_KEY, which
  is not exposed by any API.
- No employee identifier (employee_id, name, email) appears in /messages.csv.
- Aggregate counts (count(), group-by) are fine — same shape HR sees.

The grep for `cleaned_text` / `wellness_tip` / `snippet` should still turn
up zero matches. `input_text` matches inside /messages.csv because the
ciphertext export is intentional.
"""

from __future__ import annotations

import csv
import io
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import (
    APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, Query,
    Request, UploadFile, status,
)
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.database import get_db
from app.utils.audit import log_action
from app.utils.security import decode_access_token, hash_password
from app.utils.settings_store import (
    SettingValidationError, get_all_settings, get_setting, invalidate_cache, set_setting,
)


router = APIRouter(prefix="/api/admin", tags=["Admin"])
security = HTTPBearer()


# Process-start time for uptime reporting. Module-level so it tracks the worker
# rather than the request.
_START_TIME = time.time()


# ── Auth gate ─────────────────────────────────────────────────────────
def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> models.Employee:
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    employee_id = payload.get("sub")
    role = payload.get("role")
    if not employee_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Access denied — admin role required")
    employee = db.query(models.Employee).filter(
        models.Employee.employee_id == int(employee_id)
    ).first()
    if not employee:
        raise HTTPException(status_code=401, detail="User not found")
    if not employee.is_active:
        raise HTTPException(status_code=403, detail="Account has been deactivated")
    return employee


# ── Helpers ───────────────────────────────────────────────────────────
def _resolve_department(db: Session, dept_name: Optional[str]) -> Optional[models.Department]:
    """Look up a department by name (case-insensitive). Returns None for
    unknown names so callers can decide whether to 4xx."""
    if not dept_name:
        return None
    name = dept_name.strip()
    if not name:
        return None
    return db.query(models.Department).filter(models.Department.name.ilike(name)).first()


# ── Users ─────────────────────────────────────────────────────────────
@router.get("/users", response_model=list[schemas.UserAdminView])
def list_users(
    role: Optional[schemas.RoleEnum] = Query(None),
    is_active: Optional[bool] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    q = db.query(models.Employee)
    if role is not None:
        q = q.filter(models.Employee.role == models.RoleEnum(role.value))
    if is_active is not None:
        q = q.filter(models.Employee.is_active == is_active)
    rows = q.order_by(models.Employee.employee_id.desc()).offset(offset).limit(limit).all()
    return [schemas.UserAdminView.from_orm_with_department(r) for r in rows]


@router.post("/users", response_model=schemas.UserAdminView, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: schemas.UserAdminCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    if db.query(models.Employee).filter(models.Employee.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    if payload.role == schemas.RoleEnum.employee and payload.department_name is None:
        raise HTTPException(status_code=400, detail="Employees must have a department")

    department = _resolve_department(db, payload.department_name) if payload.role == schemas.RoleEnum.employee else None
    if payload.role == schemas.RoleEnum.employee and department is None:
        raise HTTPException(status_code=400, detail="Unknown department")

    new_user = models.Employee(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=models.RoleEnum(payload.role.value),
        department_id=department.department_id if department else None,
        is_verified=True,  # Admin-created accounts skip email verification.
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_action(
        db, request, current_admin, "user.create",
        target_type="employee", target_id=new_user.employee_id,
        meta={"role": payload.role.value, "email": payload.email},
    )
    return schemas.UserAdminView.from_orm_with_department(new_user)


@router.patch("/users/{user_id}", response_model=schemas.UserAdminView)
def update_user(
    user_id: int,
    payload: schemas.UserAdminUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    user = db.query(models.Employee).filter(models.Employee.employee_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    changes: dict = {}
    if payload.name is not None:
        changes["name"] = payload.name
        user.name = payload.name
    if payload.email is not None and payload.email != user.email:
        if db.query(models.Employee).filter(models.Employee.email == payload.email).first():
            raise HTTPException(status_code=400, detail="Email already in use")
        changes["email"] = payload.email
        user.email = payload.email
    if payload.role is not None:
        # Role transitions are sensitive — audit explicitly.
        new_role = models.RoleEnum(payload.role.value)
        if user.role != new_role:
            changes["role"] = payload.role.value
            user.role = new_role
            # An HR or admin with a department doesn't really make sense; clear it.
            if new_role in (models.RoleEnum.hr, models.RoleEnum.admin):
                user.department_id = None
    if payload.department_name is not None:
        dept = _resolve_department(db, payload.department_name)
        if dept is None:
            raise HTTPException(status_code=400, detail="Unknown department")
        changes["department_id"] = dept.department_id
        user.department_id = dept.department_id
    if payload.is_active is not None:
        changes["is_active"] = payload.is_active
        user.is_active = payload.is_active

    db.commit()
    db.refresh(user)
    log_action(
        db, request, current_admin, "user.update",
        target_type="employee", target_id=user.employee_id, meta=changes,
    )
    return schemas.UserAdminView.from_orm_with_department(user)


@router.post("/users/{user_id}/deactivate", response_model=schemas.UserAdminView)
def deactivate_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    if user_id == current_admin.employee_id:
        raise HTTPException(status_code=400, detail="You cannot deactivate yourself")
    user = db.query(models.Employee).filter(models.Employee.employee_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.commit()
    db.refresh(user)
    log_action(
        db, request, current_admin, "user.deactivate",
        target_type="employee", target_id=user.employee_id,
    )
    return schemas.UserAdminView.from_orm_with_department(user)


@router.post("/users/{user_id}/reactivate", response_model=schemas.UserAdminView)
def reactivate_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    user = db.query(models.Employee).filter(models.Employee.employee_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    db.commit()
    db.refresh(user)
    log_action(
        db, request, current_admin, "user.reactivate",
        target_type="employee", target_id=user.employee_id,
    )
    return schemas.UserAdminView.from_orm_with_department(user)


# ── Settings ─────────────────────────────────────────────────────────
@router.get("/settings", response_model=list[schemas.SettingView])
def get_settings(
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    return get_all_settings(db)


@router.put("/settings/{key}", response_model=schemas.SettingView)
def update_setting(
    key: str,
    payload: schemas.SettingValue,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    try:
        stored, was_clamped = set_setting(db, key, payload.value, current_admin.employee_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown setting key")
    except SettingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    log_action(
        db, request, current_admin, "settings.update",
        target_type="setting", target_id=key,
        meta={"value": stored, "submitted": payload.value, "clamped": was_clamped},
    )
    # Return the freshly merged row.
    all_settings = get_all_settings(db)
    for s in all_settings:
        if s["key"] == key:
            return s
    raise HTTPException(status_code=500, detail="Setting vanished after write")


# ── System health ─────────────────────────────────────────────────────
@router.get("/system/health")
def system_health(
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    # DB ping
    db_ok = True
    try:
        db.query(models.Employee).limit(1).all()
    except Exception:
        db_ok = False

    # Disk usage of the container's root filesystem.
    disk_total = disk_used = disk_free = 0
    try:
        usage = shutil.disk_usage("/")
        disk_total, disk_used, disk_free = usage.total, usage.used, usage.free
    except Exception:
        pass

    # Aggregate row counts — these reveal NO per-employee data.
    counts = {
        "employees": db.query(func.count(models.Employee.employee_id)).scalar() or 0,
        "reflections": db.query(func.count(models.DailyReflection.reflection_id)).scalar() or 0,
        "alarms": db.query(func.count(models.DepartmentAlarm.alarm_id)).scalar() or 0,
        "critical_alerts_open": db.query(func.count(models.CriticalKeywordAlert.alert_id))
            .filter(models.CriticalKeywordAlert.is_resolved == False).scalar() or 0,  # noqa: E712
        "activity_logs": db.query(func.count(models.ActivityLog.id)).scalar() or 0,
    }

    # Recent login failures over the last 24h — a small operational health signal.
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    recent_login_failures = (
        db.query(func.count(models.ActivityLog.id))
        .filter(models.ActivityLog.action == "login.failure")
        .filter(models.ActivityLog.created_at >= since)
        .scalar() or 0
    )

    return {
        "db_ok": db_ok,
        "uptime_seconds": int(time.time() - _START_TIME),
        "disk": {"total": disk_total, "used": disk_used, "free": disk_free},
        "counts": counts,
        "recent_login_failures_24h": recent_login_failures,
        "now": datetime.now(timezone.utc).isoformat(),
    }


# ── Activity logs ─────────────────────────────────────────────────────
@router.get("/activity-logs", response_model=list[schemas.ActivityLogView])
def list_activity_logs(
    actor_role: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    q = db.query(models.ActivityLog)
    if actor_role:
        q = q.filter(models.ActivityLog.actor_role == actor_role)
    if action:
        q = q.filter(models.ActivityLog.action == action)
    return q.order_by(desc(models.ActivityLog.created_at)).offset(offset).limit(limit).all()


# ── Model management ──────────────────────────────────────────────────
# predict.py loads from HuggingFace Hub. We expose the current hub id and let
# admins point predict.py at a different model. Real training is out of scope.
@router.get("/model")
def get_model_info(
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    current_id = get_setting(db, "model_hub_id")
    # Cache size on disk, if HF cache is present.
    cache_root = os.path.expanduser("~/.cache/huggingface")
    cache_size = 0
    if os.path.isdir(cache_root):
        for dirpath, _dirs, files in os.walk(cache_root):
            for f in files:
                try:
                    cache_size += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
    return {
        "current_model_hub_id": current_id,
        "cache_root": cache_root,
        "cache_size_bytes": cache_size,
        "device_hint": "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES") else "cpu",
    }


def _reload_predict_module() -> None:
    """Force predict.py to reload the model on next call by re-importing it."""
    import importlib
    import predict as _predict
    importlib.reload(_predict)


@router.post("/model")
def set_model_hub_id(
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    new_id = (payload.get("model_hub_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._\-/]+", new_id) or "/" not in new_id:
        raise HTTPException(status_code=400, detail="Invalid HuggingFace model ID")
    stored, _ = set_setting(db, "model_hub_id", new_id, current_admin.employee_id)
    # predict.py reads MODEL_HUB_ID at import time, so we set it then reload.
    os.environ["MODEL_HUB_ID"] = stored
    try:
        _reload_predict_module()
    except Exception as exc:
        invalidate_cache("model_hub_id")
        raise HTTPException(status_code=500, detail=f"Model reload failed: {exc}")
    log_action(
        db, request, current_admin, "model.update",
        target_type="model", target_id=stored, meta={"new_model_hub_id": stored},
    )
    return {"current_model_hub_id": stored, "reloaded": True}


# ── Departments ──────────────────────────────────────────────────────
@router.get("/departments", response_model=list[schemas.DepartmentAdminView])
def list_departments(
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    counts = dict(
        db.query(
            models.Employee.department_id, func.count(models.Employee.employee_id)
        )
        .filter(models.Employee.department_id.isnot(None))
        .group_by(models.Employee.department_id)
        .all()
    )
    rows = db.query(models.Department).order_by(models.Department.name).all()
    return [
        schemas.DepartmentAdminView(
            department_id=d.department_id,
            name=d.name if isinstance(d.name, str) else d.name.value,
            employee_count=counts.get(d.department_id, 0),
        )
        for d in rows
    ]


@router.post("/departments", response_model=schemas.DepartmentAdminView, status_code=status.HTTP_201_CREATED)
def create_department(
    payload: schemas.DepartmentAdminCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Department name is required")
    existing = db.query(models.Department).filter(models.Department.name.ilike(name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="A department with that name already exists")
    dept = models.Department(name=name)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    log_action(
        db, request, current_admin, "department.create",
        target_type="department", target_id=dept.department_id, meta={"name": name},
    )
    return schemas.DepartmentAdminView(
        department_id=dept.department_id, name=name, employee_count=0,
    )


@router.patch("/departments/{dept_id}", response_model=schemas.DepartmentAdminView)
def rename_department(
    dept_id: int,
    payload: schemas.DepartmentAdminUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    dept = db.query(models.Department).filter(models.Department.department_id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    new_name = payload.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Department name is required")
    clash = (
        db.query(models.Department)
        .filter(models.Department.name.ilike(new_name))
        .filter(models.Department.department_id != dept_id)
        .first()
    )
    if clash:
        raise HTTPException(status_code=400, detail="A department with that name already exists")
    old_name = dept.name if isinstance(dept.name, str) else dept.name.value
    dept.name = new_name
    db.commit()
    db.refresh(dept)
    log_action(
        db, request, current_admin, "department.rename",
        target_type="department", target_id=dept.department_id,
        meta={"old_name": old_name, "new_name": new_name},
    )
    emp_count = (
        db.query(func.count(models.Employee.employee_id))
        .filter(models.Employee.department_id == dept_id)
        .scalar() or 0
    )
    return schemas.DepartmentAdminView(
        department_id=dept.department_id, name=new_name, employee_count=emp_count,
    )


@router.delete("/departments/{dept_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department(
    dept_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    dept = db.query(models.Department).filter(models.Department.department_id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    attached = (
        db.query(func.count(models.Employee.employee_id))
        .filter(models.Employee.department_id == dept_id)
        .scalar() or 0
    )
    if attached:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete — {attached} employee(s) still assigned. Reassign or deactivate them first.",
        )
    name = dept.name if isinstance(dept.name, str) else dept.name.value
    db.delete(dept)
    db.commit()
    log_action(
        db, request, current_admin, "department.delete",
        target_type="department", target_id=dept_id, meta={"name": name},
    )
    return


# ── CSV export (per-submission; message stays Fernet ciphertext) ────
@router.get("/messages.csv")
def export_messages_csv(
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    """One row per reflection. The `encrypted_message` column is the raw
    Fernet token stored in `daily_reflections.input_text` — admin sees the
    same opaque ciphertext that lives in the DB and cannot decrypt it
    without REFLECTION_ENC_KEY, which is not exposed by any API endpoint.
    No employee identifier is included.
    """
    rows = (
        db.query(
            models.DailyReflection.created_at.label("created_at"),
            models.Department.name.label("department"),
            models.DailyReflection.input_text.label("encrypted_message"),
            models.DailyReflection.selected_emotion.label("selected_emotion"),
            models.SentimentAnalysis.emotion.label("predicted_emotion"),
        )
        .join(
            models.Department,
            models.Department.department_id == models.DailyReflection.department_id,
        )
        .outerjoin(
            models.SentimentAnalysis,
            models.SentimentAnalysis.reflection_id == models.DailyReflection.reflection_id,
        )
        .order_by(models.DailyReflection.created_at.desc())
        .all()
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "date",
        "department",
        "encrypted_message",
        "employee_selected_emotion",
        "emotion_prediction",
    ])
    for r in rows:
        dept_name = r.department if isinstance(r.department, str) else r.department.value
        predicted = r.predicted_emotion
        if predicted is not None and hasattr(predicted, "value"):
            predicted = predicted.value
        writer.writerow([
            r.created_at.isoformat() if r.created_at else "",
            dept_name,
            r.encrypted_message or "",
            r.selected_emotion or "",
            predicted or "",
        ])

    log_action(
        db, None, current_admin, "messages.export_csv",
        target_type="export", meta={"row_count": len(rows)},
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=moodloop-messages-{ts}.csv"},
    )


# ── Backup & restore ──────────────────────────────────────────────────
def _pg_connection_args() -> list[str]:
    parsed = urlparse(settings.DATABASE_URL)
    args = []
    if parsed.hostname:
        args += ["-h", parsed.hostname]
    if parsed.port:
        args += ["-p", str(parsed.port)]
    if parsed.username:
        args += ["-U", parsed.username]
    if parsed.path and parsed.path.startswith("/"):
        args += ["-d", parsed.path[1:]]
    return args


def _pg_env() -> dict[str, str]:
    parsed = urlparse(settings.DATABASE_URL)
    env = os.environ.copy()
    if parsed.password:
        env["PGPASSWORD"] = parsed.password
    return env


@router.post("/backup")
def backup_db(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"moodloop-backup-{ts}.sql"

    proc = subprocess.Popen(
        ["pg_dump", "--no-owner", "--no-privileges", *_pg_connection_args()],
        env=_pg_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def stream():
        try:
            assert proc.stdout is not None
            for chunk in iter(lambda: proc.stdout.read(8192), b""):
                yield chunk
        finally:
            proc.wait()

    log_action(
        db, request, current_admin, "backup.create",
        target_type="backup", target_id=filename,
    )
    return StreamingResponse(
        stream(),
        media_type="application/sql",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/restore")
async def restore_db(
    request: Request,
    file: UploadFile = File(...),
    confirm: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Employee = Depends(get_current_admin),
):
    if confirm != "RESTORE":
        raise HTTPException(status_code=400, detail="Restore requires confirm=RESTORE")
    if not file.filename or not file.filename.endswith(".sql"):
        raise HTTPException(status_code=400, detail="Upload a .sql file")

    # Pre-restore backup — captured to disk so we can point at it from the log.
    pre_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pre_backup_path = f"/tmp/pre-restore-{pre_ts}.sql"
    with open(pre_backup_path, "wb") as fp:
        result = subprocess.run(
            ["pg_dump", "--no-owner", "--no-privileges", *_pg_connection_args()],
            env=_pg_env(), stdout=fp, stderr=subprocess.PIPE,
        )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Pre-restore backup failed: {result.stderr.decode()[:500]}")

    # Save the uploaded SQL to a temp file and replay it.
    with tempfile.NamedTemporaryFile("wb", suffix=".sql", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["psql", "-v", "ON_ERROR_STOP=1", *_pg_connection_args(), "-f", tmp_path],
            env=_pg_env(), capture_output=True,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if result.returncode != 0:
        log_action(
            db, request, current_admin, "restore.failure",
            target_type="backup", target_id=file.filename,
            meta={"pre_backup_path": pre_backup_path, "stderr": result.stderr.decode()[:500]},
        )
        raise HTTPException(status_code=500, detail=f"Restore failed: {result.stderr.decode()[:500]}")

    log_action(
        db, request, current_admin, "restore.success",
        target_type="backup", target_id=file.filename,
        meta={"pre_backup_path": pre_backup_path},
    )
    return {"restored": True, "pre_restore_backup": pre_backup_path}


# ── Retention helper (callable from the scheduler) ─────────────────────
def enforce_retention(db: Session) -> int:
    """Hard-delete reflections (and dependents) older than the retention TTL.
    Returns the number of reflections purged. Logs an aggregate audit row only."""
    days = int(get_setting(db, "reflection_retention_days"))
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    old_reflection_ids = [
        r[0] for r in db.query(models.DailyReflection.reflection_id)
        .filter(models.DailyReflection.created_at < cutoff)
        .all()
    ]
    if not old_reflection_ids:
        return 0

    # Order matters — children first to satisfy FKs.
    db.query(models.CriticalKeywordAlert).filter(
        models.CriticalKeywordAlert.reflection_id.in_(old_reflection_ids)
    ).delete(synchronize_session=False)
    db.query(models.SentimentAnalysis).filter(
        models.SentimentAnalysis.reflection_id.in_(old_reflection_ids)
    ).delete(synchronize_session=False)
    db.query(models.DailyReflection).filter(
        models.DailyReflection.reflection_id.in_(old_reflection_ids)
    ).delete(synchronize_session=False)

    entry = models.ActivityLog(
        actor_employee_id=None,
        actor_role="system",
        action="retention.purge",
        target_type="reflection",
        target_id=None,
        meta={"purged": len(old_reflection_ids), "older_than_days": days},
    )
    db.add(entry)
    db.commit()
    return len(old_reflection_ids)
