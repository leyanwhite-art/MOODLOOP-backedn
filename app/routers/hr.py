from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from app.database import get_db
from app.models import Employee, DailyReflection, SentimentAnalysis, Department
router = APIRouter(prefix="/api/hr", tags=["HR"])

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
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


@router.get("/departments")
def get_departments(db: Session = Depends(get_db)):
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


@router.get("/monthly-trends")
def get_monthly_trends(db: Session = Depends(get_db)):
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


@router.get("/mood-distribution")
def get_mood_distribution(db: Session = Depends(get_db)):
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


@router.get("/yearly-trends")
def get_yearly_trends(db: Session = Depends(get_db)):
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
    