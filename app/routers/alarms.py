from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.routers.users import get_current_user, hr_only
from app.utils.alarm import run_daily_alarm_check, calculate_department_alarm

router = APIRouter(prefix="/alarms", tags=["Alarms"])

# Get all active alarms (HR only)
@router.get("/", response_model=list[schemas.AlarmResponse])
def get_all_alarms(
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(hr_only)
):
    return db.query(models.DepartmentAlarm).order_by(
        models.DepartmentAlarm.created_at.desc()
    ).all()

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