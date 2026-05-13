import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import crud, schemas, models
from app.routers.users import get_current_user
from app.utils.text_cleaner import clean_arabic_text, validate_arabic_text
from app.utils.keyword_alarm import detect_keywords
from app.utils.crypto import encrypt_text, decrypt_text, DecryptionError
from app.utils.settings_store import get_setting
from datetime import datetime, timedelta, timezone
from predict import predict_emotion
from app.services.gemini import generate_wellness_tip

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


def _safe_decrypt(value: str | None) -> str | None:
    """Decrypt a stored token, or pass through if it isn't a Fernet token
    (e.g. legacy rows that pre-date the encryption migration)."""
    if value is None:
        return None
    try:
        return decrypt_text(value)
    except DecryptionError:
        # Surfaced to the owner only — admins/HR never reach this code path.
        raise HTTPException(
            status_code=500,
            detail="Stored reflection could not be decrypted. Contact your administrator.",
        )


@router.post("/", response_model=schemas.ReflectionResponse)
async def create_reflection(
    reflection: schemas.ReflectionCreate,
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(get_current_user)
):
    # Only employees can submit reflections. HR and admin cannot.
    if current_user.role != models.RoleEnum.employee:
        raise HTTPException(status_code=403, detail="Only employees can submit reflections")

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

    max_per_day = int(get_setting(db, "max_reflections_per_day"))
    cooldown_hours = int(get_setting(db, "reflection_cooldown_hours"))

    # Check max reflections per day
    today_reflections = db.query(models.DailyReflection).filter(
        models.DailyReflection.employee_id == current_user.employee_id,
        models.DailyReflection.created_at >= today_start
    ).count()

    if today_reflections >= max_per_day:
        raise HTTPException(
            status_code=400,
            detail=f"You have reached the maximum of {max_per_day} reflections per day",
        )

    # Cooldown between reflections
    last_reflection = db.query(models.DailyReflection).filter(
        models.DailyReflection.employee_id == current_user.employee_id
    ).order_by(models.DailyReflection.created_at.desc()).first()

    if last_reflection and cooldown_hours > 0:
        time_diff = now - last_reflection.created_at
        cooldown = timedelta(hours=cooldown_hours)
        if time_diff < cooldown:
            remaining = cooldown - time_diff
            minutes = int(remaining.total_seconds() / 60)
            raise HTTPException(
                status_code=400,
                detail=f"Please wait {minutes} minutes before submitting another reflection"
            )

    # Clean text with spaCy (strips PII)
    plaintext_raw = reflection.input_text
    plaintext_cleaned = clean_arabic_text(plaintext_raw)

    # Persist ENCRYPTED text only. Plaintext stays in-process for prediction/keyword scan.
    db_reflection = models.DailyReflection(
        employee_id=current_user.employee_id,
        department_id=current_user.department_id,
        input_text=encrypt_text(plaintext_raw),
        cleaned_text=encrypt_text(plaintext_cleaned),
        wellness_tip=None,
        selected_emotion=(reflection.selected_emotion or None),
    )
    db.add(db_reflection)
    db.flush()

    # Run AraBERT emotion prediction off the event loop (on plaintext)
    prediction = await asyncio.to_thread(predict_emotion, plaintext_raw)
    emotion_label = prediction["emotion"]

    db.add(models.SentimentAnalysis(
        reflection_id=db_reflection.reflection_id,
        department_id=current_user.department_id,
        sentiment=EMOTION_TO_SENTIMENT[emotion_label],
        emotion=models.EmotionEnum(emotion_label.lower()),
        confidence=prediction["intensity"],
    ))

    # Generate the MoodLoop wellness tip via Gemini (off the event loop —
    # the SDK call is sync/blocking under the hood).
    wellness_tip = await asyncio.to_thread(
        generate_wellness_tip,
        plaintext_raw,
        emotion_label.lower(),
    )
    db_reflection.wellness_tip = wellness_tip

    # Scan raw plaintext input for crisis keywords. The snippet IS the raw text,
    # so encrypt it too — HR/admin should never see the original phrasing, only
    # the matched keyword + an opaque audit reference.
    for matched_kw, snippet in detect_keywords(plaintext_raw):
        db.add(models.CriticalKeywordAlert(
            reflection_id=db_reflection.reflection_id,
            employee_id=current_user.employee_id,
            department_id=current_user.department_id,
            matched_keyword=matched_kw,
            snippet=encrypt_text(snippet),
            severity=models.SeverityEnum.critical,
            is_resolved=False,
        ))

    db.commit()
    db.refresh(db_reflection)

    # Return plaintext to the owner only (this is their own submission echoing back).
    response = schemas.ReflectionResponse(
        reflection_id=db_reflection.reflection_id,
        employee_id=db_reflection.employee_id,
        department_id=db_reflection.department_id,
        input_text=plaintext_raw,
        cleaned_text=plaintext_cleaned,
        wellness_tip=db_reflection.wellness_tip,
        created_at=db_reflection.created_at,
        predicted_emotion=emotion_label.lower(),
        confidence=prediction["intensity"],
    )
    return response


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
    rows = crud.get_reflections_by_employee(db, current_user.employee_id)
    out: list[schemas.ReflectionResponse] = []
    for r in rows:
        out.append(schemas.ReflectionResponse(
            reflection_id=r.reflection_id,
            employee_id=r.employee_id,
            department_id=r.department_id,
            input_text=_safe_decrypt(r.input_text) or "",
            cleaned_text=_safe_decrypt(r.cleaned_text),
            wellness_tip=r.wellness_tip,
            created_at=r.created_at,
        ))
    return out
