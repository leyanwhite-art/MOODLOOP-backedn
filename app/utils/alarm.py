from sqlalchemy.orm import Session
from app import models
from datetime import datetime, timedelta

def calculate_department_alarm(db: Session, department_id: int):
    # Get last 7 days window
    window_start = datetime.now() - timedelta(days=7)
    window_end = datetime.now()

    # Get all sentiment analyses for this department in the last 7 days
    analyses = db.query(models.SentimentAnalysis).filter(
        models.SentimentAnalysis.department_id == department_id,
        models.SentimentAnalysis.analyzed_at >= window_start
    ).all()

    total = len(analyses)

    # K-anonymity check — need at least 5 employees
    employee_ids = set(
        db.query(models.DailyReflection.employee_id).filter(
            models.DailyReflection.department_id == department_id,
            models.DailyReflection.created_at >= window_start
        ).distinct().all()
    )

    if len(employee_ids) < 5:
        print(f"Department {department_id}: Not enough employees for K-anonymity ({len(employee_ids)}/5)")
        return None

    if total == 0:
        return None

    # Calculate negative ratio
    negative_count = sum(1 for a in analyses if a.sentiment == models.SentimentEnum.negative)
    negative_ratio = negative_count / total

    # Determine severity
    if negative_ratio >= 0.80:
        severity = models.SeverityEnum.critical
        severity_label = "Critical"
    elif negative_ratio >= 0.65:
        severity = models.SeverityEnum.high
        severity_label = "High"
    elif negative_ratio >= 0.50:
        severity = models.SeverityEnum.medium
        severity_label = "Medium"
    elif negative_ratio >= 0.30:
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
        created_at=datetime.now()
    )
    db.add(alarm)
    db.commit()
    db.refresh(alarm)

    print(f"✅ Alarm created for department {dept_name}: {severity_label}")
    return alarm

def run_daily_alarm_check(db: Session):
    print(f"🔔 Running daily alarm check at {datetime.now()}")
    departments = db.query(models.Department).all()
    for dept in departments:
        calculate_department_alarm(db, dept.department_id)
    print("✅ Daily alarm check completed!") 