from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app import models, schemas
from app.routers.users import get_current_user, hr_only
from app.utils.alarm import run_daily_alarm_check, calculate_department_alarm
from app.utils.dept_display import dept_display

router = APIRouter(prefix="/alarms", tags=["Alarms"])

# Get all active alarms (HR only).
# Response is built manually (no response_model) so we can include the
# department display name without altering the AlarmResponse schema, which
# the other endpoints in this file still use.
@router.get("/")
def get_all_alarms(
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(hr_only),
):
    # Severity order — critical first, low last. Mapped to integers so the
    # SQLAlchemy ORDER BY works across both Postgres and SQLite during dev.
    severity_rank = {
        models.SeverityEnum.critical: 0,
        models.SeverityEnum.high:     1,
        models.SeverityEnum.medium:   2,
        models.SeverityEnum.low:      3,
    }

    alarms = (
        db.query(models.DepartmentAlarm)
        .options(joinedload(models.DepartmentAlarm.department))
        .all()
    )

    alarms.sort(key=lambda a: (severity_rank.get(a.severity, 99), -a.negative_ratio))

    return [
        {
            "alarm_id":        a.alarm_id,
            "department_id":   a.department_id,
            "department_name": dept_display(a.department),
            "severity":        a.severity.value if hasattr(a.severity, "value") else a.severity,
            "negative_ratio":  a.negative_ratio,
            "analyses_count":  a.analyses_count,
            "window_start":    a.window_start.isoformat() if a.window_start else None,
            "window_end":      a.window_end.isoformat()   if a.window_end   else None,
            "created_at":      a.created_at.isoformat()   if a.created_at   else None,
        }
        for a in alarms
    ]

# Get alarms by severity (HR only)
@router.get("/severity/{severity}", response_model=list[schemas.AlarmResponse])
def get_alarms_by_severity(
    severity: str,
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(hr_only)
):
    return db.query(models.DepartmentAlarm).filter(
        models.DepartmentAlarm.severity == severity
    ).all()

# Get alarm for specific department (HR only)
@router.get("/department/{department_id}", response_model=schemas.AlarmResponse)
def get_department_alarm(
    department_id: int,
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(hr_only)
):
    alarm = db.query(models.DepartmentAlarm).filter(
        models.DepartmentAlarm.department_id == department_id
    ).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="No alarm for this department")
    return alarm

# Manually trigger alarm check (HR only) - for testing
@router.post("/trigger")
def trigger_alarm_check(
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(hr_only)
):
    run_daily_alarm_check(db)
    return {"message": "Alarm check completed!"} 