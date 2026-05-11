from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta

from database import get_db
from models import DailyReflection, SentimentAnalysis, Employee
from schemas import ReflectionCreate, ReflectionResponse, EmotionHistory

# [span_3](start_span)الخطوة 6: استيراد دالة التنبؤ من ملفك[span_3](end_span)
from predict import predict_emotion 

router = APIRouter(prefix="/api/employee", tags=["Employee"])


@router.post("/reflection", response_model=ReflectionResponse)
def submit_reflection(data: ReflectionCreate, db: Session = Depends(get_db)):

    employee = db.query(Employee).filter(
        Employee.employee_id == data.employee_id
    ).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)
    existing = db.query(DailyReflection).filter(
        DailyReflection.employee_id == data.employee_id,
        DailyReflection.created_at >= today_start,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already submitted today")

    # --- الجزء الخاص بنموذج الذكاء الاصطناعي ---
    
    # 1. [span_4](start_span)تحليل النص باستخدام النموذج الذي قمتِ بتدريبه[span_4](end_span)
    result = predict_emotion(data.text)
    
    detected_emotion = result["emotion"]      # الشعور المكتشف (مثل Stress أو Happiness)
    confidence       = result["intensity"]    # نسبة الثقة (مثل 0.64)
    all_scores       = result["all_scores"]   # توزيع باقي المشاعر
    
    # يمكنكِ لاحقاً تخصيص هذه الرسائل بناءً على نوع الشعور المكتشف
    ai_tip = "شكراً لمشاركتنا شعورك، خذ نفساً عميقاً وفكر في إنجازاتك اليوم."

    # 2. حفظ سجل التأمل
    reflection = DailyReflection(
        employee_id=data.employee_id,
        department_id=employee.department_id,
        input_text=data.text,
        wellness_tip=ai_tip,
    )
    db.add(reflection)
    db.flush()

    # 3. [span_5](start_span)حفظ نتائج تحليل المشاعر المستخرجة من AraBERT[span_5](end_span)
    analysis = SentimentAnalysis(
        reflection_id=reflection.reflection_id,
        department_id=employee.department_id,
        sentiment=detected_emotion, # حفظ الشعور في خانة sentiment أو emotion حسب تصميم جدولك
        emotion=detected_emotion,
        confidence=confidence,
    )
    db.add(analysis)
    db.commit()
    db.refresh(reflection)

    # 4. إعادة النتيجة النهائية للـ Frontend
    return {
        "reflection_id":    reflection.reflection_id,
        "detected_emotion": detected_emotion,
        "intensity":        confidence,
        "wellness_tip":     ai_tip,
        "all_scores":       all_scores 
    }


@router.get("/my-emotions/{employee_id}", response_model=List[EmotionHistory])
def get_my_emotions(
    employee_id: int,
    days: int = 30,
    db: Session = Depends(get_db)
):
    employee = db.query(Employee).filter(
        Employee.employee_id == employee_id
    ).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    since = datetime.utcnow() - timedelta(days=days)

    results = (
        db.query(
            SentimentAnalysis.emotion,
            SentimentAnalysis.confidence,
            DailyReflection.created_at,
        )
        .join(DailyReflection,
              DailyReflection.reflection_id == SentimentAnalysis.reflection_id)
        .filter(
            DailyReflection.employee_id == employee_id,
            DailyReflection.created_at >= since,
        )
        .order_by(DailyReflection.created_at.asc())
        .all()
    )

    return [
        {
            "emotion_type":         r.emotion,
            "emotion_intensity":    round(r.confidence, 2),
            "reflection_timestamp": r.created_at,
        }
        for r in results
    ]
    
    