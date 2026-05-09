from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import crud, schemas, models
from app.routers.users import get_current_user
from app.utils.text_cleaner import clean_arabic_text, validate_arabic_text
from datetime import datetime, timedelta

router = APIRouter(prefix="/reflections", tags=["Reflections"])

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

    # Check max 3 reflections per day
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
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
        time_diff = datetime.now() - last_reflection.created_at
        if time_diff < timedelta(hours=2):
            remaining = timedelta(hours=2) - time_diff
            minutes = int(remaining.total_seconds() / 60)
            raise HTTPException(
                status_code=400,
                detail=f"Please wait {minutes} minutes before submitting another reflection"
            )

    # Clean text with spaCy
    cleaned_text = clean_arabic_text(reflection.input_text)

    # Save reflection
    db_reflection = models.DailyReflection(
        employee_id=current_user.employee_id,
        department_id=current_user.department_id,
        input_text=reflection.input_text,
        wellness_tip=None
    )
    db.add(db_reflection)
    db.commit()
    db.refresh(db_reflection)

    return db_reflection

@router.get("/my", response_model=list[schemas.ReflectionResponse])
def get_my_reflections(
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(get_current_user)
):
    return crud.get_reflections_by_employee(db, current_user.employee_id) 