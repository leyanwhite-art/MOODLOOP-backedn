from sqlalchemy.orm import Session
from app import models
from app.utils.settings_store import get_setting
from datetime import datetime, timedelta, timezone


def calculate_department_alarm(db: Session, department_id: int):
    # Use UTC, but strip tzinfo to match the DB columns (which don't store tz)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    window_start = now_utc - timedelta(days=7)
    window_end = now_utc

    # Get all sentiment analyses for this department in the last 7 days
    analyses = db.query(models.SentimentAnalysis).filter(
        models.SentimentAnalysis.department_id == department_id,
        models.SentimentAnalysis.analyzed_at >= window_start
    ).all()

    total = len(analyses)

    # K-anonymity check — floor comes from system_settings; hard min of 5 is
    # enforced when the setting is written, so a misconfiguration can never
    # lower it below the privacy contract.
    k_anon_floor = int(get_setting(db, "alarm_k_anonymity_floor"))
    employee_ids = set(
        db.query(models.DailyReflection.employee_id).filter(
            models.DailyReflection.department_id == department_id,
            models.DailyReflection.created_at >= window_start
        ).distinct().all()
    )

    if len(employee_ids) < k_anon_floor:
        print(f"Department {department_id}: Not enough employees for K-anonymity ({len(employee_ids)}/{k_anon_floor})")
        return None

    if total == 0:
        return None

    # Calculate negative ratio
    negative_count = sum(1 for a in analyses if a.sentiment == models.SentimentEnum.negative)
    negative_ratio = negative_count / total

    # Thresholds are admin-tunable via system_settings.
    t_critical = float(get_setting(db, "alarm_threshold_critical"))
    t_high = float(get_setting(db, "alarm_threshold_high"))
    t_medium = float(get_setting(db, "alarm_threshold_medium"))
    t_low = float(get_setting(db, "alarm_threshold_low"))

    if negative_ratio >= t_critical:
        severity = models.SeverityEnum.critical
        severity_label = "Critical"
    elif negative_ratio >= t_high:
        severity = models.SeverityEnum.high
        severity_label = "High"
    elif negative_ratio >= t_medium:
        severity = models.SeverityEnum.medium
        severity_label = "Medium"
    elif negative_ratio >= t_low:
        severity = models.SeverityEnum.low
        severity_label = "Low"
    else:
        return None

    # Get department name
    department = db.query(models.Department).filter(
        models.Department.department_id == department_id
    ).first()

    # Build message
    dept_name = department.name.value if hasattr(department.name, 'value') else department.name
    message = f"""⚠️ {dept_name} Department
Severity: {severity_label}
{round(negative_ratio * 100)}% of employees reported negative sentiment
Period: Last 7 days
Analyses count: {total}"""

    # Delete old alarm for this department
    db.query(models.DepartmentAlarm).filter(
        models.DepartmentAlarm.department_id == department_id
    ).delete()

    # Create new alarm
    alarm = models.DepartmentAlarm(
        department_id=department_id,
        severity=severity,
        message=message,
        negative_ratio=negative_ratio,
        analyses_count=total,
        window_start=window_start,
        window_end=window_end,
        created_at=now_utc
    )
    db.add(alarm)
    db.commit()
    db.refresh(alarm)

    print(f"✅ Alarm created for department {dept_name}: {severity_label}")
    return alarm


def run_daily_alarm_check(db: Session):
    print(f"🔔 Running daily alarm check at {datetime.now(timezone.utc).isoformat()}")
    departments = db.query(models.Department).all()
    for dept in departments:
        calculate_department_alarm(db, dept.department_id)
    print("✅ Daily alarm check completed!") 