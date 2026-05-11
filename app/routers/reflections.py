import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import crud, schemas, models
from app.routers.users import get_current_user
from app.utils.text_cleaner import clean_arabic_text, validate_arabic_text
from app.utils.keyword_alarm import detect_keywords
from datetime import datetime, timedelta, timezone
from predict import predict_emotion

router = APIRouter(prefix="/reflections", tags=["Reflections"])

EMOTION_TO_SENTIMENT = {
    "Happiness": models.SentimentEnum.positive,
    "Motivation": models.SentimentEnum.positive,
    "Cooperation": models.SentimentEnum.positive,
    "Neutral": models.SentimentEnum.neutral,
    "Stress": models.SentimentEnum.negative,
    "Sadness": models.SentimentEnum.negative,
    "Anger": models.SentimentEnum.negative,
}


@router.post("/", response_model=schemas.ReflectionResponse)
async def create_reflection(
    reflection: schemas.ReflectionCreate,
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(get_current_user)
):
    # HR cannot submit reflections
    if current_user.role == models.RoleEnum.hr:
        raise HTTPException(status_code=403, detail="HR cannot submit reflections")

    # Validate Arabic text
    if not validate_arabic_text(reflection.input_text):
        raise HTTPException(status_code=400, detail="Reflection must be in Arabic")

    # Validate text length
    if len(reflection.input_text) < 100:
        raise HTTPException(status_code=400, detail="Reflection must be at least 100 characters")

    if len(reflection.input_text) > 1000:
        raise HTTPException(status_code=400, detail="Reflection cannot exceed 1000 characters")

    # Compute "now" once, in UTC, tz-stripped to match DB columns
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Check max 3 reflections per day
    today_reflections = db.query(models.DailyReflection).filter(
        models.DailyReflection.employee_id == current_user.employee_id,
        models.DailyReflection.created_at >= today_start
    ).count()

    if today_reflections >= 3:
        raise HTTPException(status_code=400, detail="You have reached the maximum of 3 reflections per day")

    # Check 2 hours between reflections
    last_reflection = db.query(models.DailyReflection).filter(
        models.DailyReflection.employee_id == current_user.employee_id
    ).order_by(models.DailyReflection.created_at.desc()).first()

    if last_reflection:
        time_diff = now - last_reflection.created_at
        if time_diff < timedelta(hours=2):
            remaining = timedelta(hours=2) - time_diff
            minutes = int(remaining.total_seconds() / 60)
            raise HTTPException(
                status_code=400,
                detail=f"Please wait {minutes} minutes before submitting another reflection"
            )

    # Clean text with spaCy
    cleaned_text = clean_arabic_text(reflection.input_text)

    # Save reflection (flush to obtain reflection_id without committing yet,
    # so the SentimentAnalysis insert below lives in the same transaction)
    db_reflection = models.DailyReflection(
        employee_id=current_user.employee_id,
        department_id=current_user.department_id,
        input_text=reflection.input_text,
        cleaned_text=cleaned_text,
        wellness_tip=None
    )
    db.add(db_reflection)
    db.flush()

    # Run AraBERT emotion prediction off the event loop
    prediction = await asyncio.to_thread(predict_emotion, reflection.input_text)
    emotion_label = prediction["emotion"]

    db.add(models.SentimentAnalysis(
        reflection_id=db_reflection.reflection_id,
        department_id=current_user.department_id,
        sentiment=EMOTION_TO_SENTIMENT[emotion_label],
        emotion=models.EmotionEnum(emotion_label.lower()),
        confidence=prediction["intensity"],
    ))

    # Scan raw input for crisis keywords. Use the un-cleaned text so signals
    # that co-occur with PII still trigger.
    for matched_kw, snippet in detect_keywords(reflection.input_text):
        db.add(models.CriticalKeywordAlert(
            reflection_id=db_reflection.reflection_id,
            employee_id=current_user.employee_id,
            department_id=current_user.department_id,
            matched_keyword=matched_kw,
            snippet=snippet,
            severity=models.SeverityEnum.critical,
            is_resolved=False,
        ))

    db.commit()
    db.refresh(db_reflection)

    db_reflection.predicted_emotion = emotion_label.lower()
    db_reflection.confidence = prediction["intensity"]

    return db_reflection


@router.post("/predict-only", response_model=schemas.EmotionPredictionResponse)
async def predict_only(
    body: schemas.EmotionPredictionRequest,
    current_user: models.Employee = Depends(get_current_user),
):
    """Run the AraBERT model without writing to the DB or applying cooldowns.
    Dev helper for the frontend /test-model page."""
    return await asyncio.to_thread(predict_emotion, body.input_text)


@router.get("/my", response_model=list[schemas.ReflectionResponse])
def get_my_reflections(
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(get_current_user)
):
    return crud.get_reflections_by_employee(db, current_user.employee_id) 