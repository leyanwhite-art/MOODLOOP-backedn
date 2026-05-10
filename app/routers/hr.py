from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import date
import sqlalchemy as sa

from app.database import get_db
from app.models import Employee, DailyReflection, SentimentAnalysis, Department, RoleEnum
from app.utils.security import decode_access_token

router = APIRouter(prefix="/api/hr", tags=["HR"])
security = HTTPBearer()


# ── JWT Protection ───────────────────────────────────────────
def get_current_hr(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    employee_id = payload.get("sub")
    role = payload.get("role")
    if not employee_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    if role != "hr":
        raise HTTPException(status_code=403, detail="Access denied — HR role required")
    employee = db.query(Employee).filter(
        Employee.employee_id == int(employee_id)
    ).first()
    if not employee:
        raise HTTPException(status_code=401, detail="User not found")
    return employee
    current_user: Employee = Depends(get_current_hr)


# ── 1. Stats ─────────────────────────────────────────────────
@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_hr)
):
    total_messages = db.query(DailyReflection).count()
    avg_conf = db.query(func.avg(SentimentAnalysis.confidence)).scalar() or 0
    avg_mood = round(float(avg_conf) * 5, 1)
    active_depts = db.query(
        func.count(func.distinct(DailyReflection.department_id))
    ).scalar() or 0

    return {
        "totalMessages": total_messages,
        "avgMoodScore":  f"{avg_mood}/5.0",
        "departments":   str(active_depts),
        "issuesFlagged": "0",
    }
current_user: Employee = Depends(get_current_hr)

# ── 2. Departments ───────────────────────────────────────────
@router.get("/departments")
def get_departments(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_hr)
):
    msg_results = (
        db.query(
            Department.name,
            func.count(DailyReflection.reflection_id).label("messages")
        )
        .join(DailyReflection,
              DailyReflection.department_id == Department.department_id)
        .group_by(Department.name)
        .all()
    )

    emp_results = (
        db.query(
            Department.name,
            func.count(Employee.employee_id).label("employees")
        )
        .join(Employee,
              Employee.department_id == Department.department_id)
        .group_by(Department.name)
        .all()
    )

    emp_map = {r.name.value: r.employees for r in emp_results}

    display_names = {
        "accounting":      "Accounting",
        "maintenance":     "Maintenance",
        "human_resources": "HR",
        "it":              "IT",
        "sales":           "Sales",
        "marketing":       "Marketing",
    }

    return [
        {
            "name":      display_names.get(r.name.value, r.name.value),
            "messages":  r.messages,
            "employees": emp_map.get(r.name.value, 0),
        }
        for r in msg_results
    ]
current_user: Employee = Depends(get_current_hr)

# ── 3. Monthly trends ────────────────────────────────────────
@router.get("/monthly-trends")
def get_monthly_trends(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_hr)
):
    results = (
        db.query(
            extract("month", DailyReflection.created_at).label("month"),
            func.avg(SentimentAnalysis.confidence).label("avg_conf")
        )
        .join(SentimentAnalysis,
              SentimentAnalysis.reflection_id == DailyReflection.reflection_id)
        .group_by("month")
        .order_by("month")
        .all()
    )

    month_names = {
        1: "Jan", 2: "Feb", 3: "Mar",  4: "Apr",
        5: "May", 6: "Jun", 7: "Jul",  8: "Aug",
        9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
    }

    return [
        {
            "month": month_names[int(r.month)],
            "score": round(float(r.avg_conf) * 5, 1)
        }
        for r in results
    ]

current_user: Employee = Depends(get_current_hr)
# ── 4. Mood distribution ─────────────────────────────────────
@router.get("/mood-distribution")
def get_mood_distribution(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_hr)
):
    results = (
        db.query(
            SentimentAnalysis.emotion,
            func.count().label("count")
        )
        .group_by(SentimentAnalysis.emotion)
        .all()
    )

    total = sum(r.count for r in results)
    if total == 0:
        return []

    emotion_map = {
        "happiness":   {"name": "Happiness",   "nameAr": "السعادة",  "color": "#22c55e"},
        "motivation":  {"name": "Motivation",  "nameAr": "الدافعية", "color": "#f97316"},
        "cooperation": {"name": "Cooperation", "nameAr": "التعاون",  "color": "#3b82f6"},
        "neutral":     {"name": "Calmness",    "nameAr": "الهدوء",   "color": "#6b7280"},
        "stress":      {"name": "Stress",      "nameAr": "التوتر",   "color": "#eab308"},
        "anger":       {"name": "Frustration", "nameAr": "الإحباط",  "color": "#ef4444"},
        "sadness":     {"name": "Sadness",     "nameAr": "الحزن",    "color": "#8b5cf6"},
    }

    return [
        {
            "name":   emotion_map[r.emotion.value]["name"],
            "nameAr": emotion_map[r.emotion.value]["nameAr"],
            "value":  round(r.count / total * 100),
            "color":  emotion_map[r.emotion.value]["color"],
        }
        for r in results
        if r.emotion.value in emotion_map
    ]
current_user: Employee = Depends(get_current_hr)

# ── 5. Yearly trends ─────────────────────────────────────────
@router.get("/yearly-trends")
def get_yearly_trends(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_hr)
):
    results = (
        db.query(
            extract("year", DailyReflection.created_at).label("year"),
            func.avg(SentimentAnalysis.confidence).label("avg_conf")
        )
        .join(SentimentAnalysis,
              SentimentAnalysis.reflection_id == DailyReflection.reflection_id)
        .group_by("year")
        .order_by("year")
        .all()
    )

    return [
        {
            "year":  str(int(r.year)),
            "score": round(float(r.avg_conf) * 5, 1)
        }
        for r in results
    ]
current_user: Employee = Depends(get_current_hr)

# ── 6. Messages ──────────────────────────────────────────────
@router.get("/messages")
def get_messages(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_hr)
):
    results = (
        db.query(
            Department.name,
            SentimentAnalysis.emotion,
            func.count(func.distinct(DailyReflection.employee_id)).label("employee_count"),
            func.cast(DailyReflection.created_at, sa.Date).label("date"),
        )
        .join(DailyReflection,
              DailyReflection.department_id == Department.department_id)
        .join(SentimentAnalysis,
              SentimentAnalysis.reflection_id == DailyReflection.reflection_id)
        .group_by(
            Department.name,
            SentimentAnalysis.emotion,
            func.cast(DailyReflection.created_at, sa.Date)
        )
        .order_by(func.cast(DailyReflection.created_at, sa.Date).desc())
        .all()
    )

    display_names = {
        "accounting":      "Accounting Department",
        "maintenance":     "Maintenance Department",
        "human_resources": "HR Department",
        "it":              "IT Department",
        "sales":           "Sales Department",
        "marketing":       "Marketing Department",
    }

    emotion_display = {
        "happiness":   "Happiness / Satisfaction",
        "motivation":  "Motivation / Excitement",
        "cooperation": "Cooperation / Team Spirit",
        "neutral":     "Calmness / Neutral",
        "stress":      "Stress / Anxiety",
        "anger":       "Frustration / Anger",
        "sadness":     "Sadness / Burnout",
    }

    themes_map = {
        "happiness":   ["Team Collaboration", "Achievement", "Positive Environment"],
        "motivation":  ["Target Achievement", "Team Spirit", "Recognition"],
        "cooperation": ["Teamwork", "Process Efficiency", "Support"],
        "neutral":     ["Work-Life Balance", "Flexible Schedule", "Employee Support"],
        "stress":      ["Workload Management", "Time Pressure", "Task Distribution"],
        "anger":       ["Equipment & Tools", "Process Improvement", "Support Needs"],
        "sadness":     ["Burnout Prevention", "Workload", "Mental Health"],
    }

    messages = []
    for i, r in enumerate(results):
        emotion_val = r.emotion.value
        dept_display = display_names.get(r.name.value, r.name.value)
        emotion_label = emotion_display.get(emotion_val, emotion_val)
        themes = themes_map.get(emotion_val, [])
        count = r.employee_count

        ai_analysis = (
            f"AI detected {count} employee(s) with {emotion_label.lower()} sentiment. "
            f"Common patterns include {', '.join(themes[:2]).lower()} concerns."
        )

        messages.append({
            "id":            str(i + 1),
            "department":    dept_display,
            "emotion":       emotion_label,
            "employeeCount": count,
            "date":          r.date.strftime("%m/%d/%Y"),
            "themes":        themes,
            "aiAnalysis":    ai_analysis,
            "responded":     False,
            "message":       "",
        })

    return messages
    from app.schemas import HRProfileUpdate

# ── 7. Get HR profile ────────────────────────────────────────
@router.get("/profile")
def get_profile(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_hr)
):
    return {
        "employee_id": current_user.employee_id,
        "name":        current_user.name,
        "email":       current_user.email,
        "role":        current_user.role.value,
        "position":    "HR Manager",
        "phone":       "",
        "bio":         "",
        "is_verified": current_user.is_verified,
    }


# ── 8. Update HR profile ─────────────────────────────────────
@router.put("/profile")
def update_profile(
    data: dict,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_hr)
):
    if "name" in data and data["name"]:
        current_user.name = data["name"]

    db.commit()
    db.refresh(current_user)

    return {
        "employee_id": current_user.employee_id,
        "name":        current_user.name,
        "email":       current_user.email,
        "message":     "Profile updated successfully"
    }
    