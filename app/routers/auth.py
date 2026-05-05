from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import crud, schemas, models
from app.utils.security import verify_password, create_access_token, hash_password
from app.utils.email import send_verification_email, send_reset_email
import secrets
from datetime import datetime, timedelta

router = APIRouter(prefix="/auth", tags=["Auth"])

# Employee Register
@router.post("/register", response_model=schemas.EmployeeResponse)
async def register(employee: schemas.EmployeeCreate, db: Session = Depends(get_db)):
    existing = crud.get_employee_by_email(db, employee.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    verification_token = secrets.token_urlsafe(32)
    db_employee = crud.create_employee(db, employee)
    db_employee.verification_token = verification_token
    db_employee.is_verified = False
    db.commit()
    db.refresh(db_employee)
    db_employee = db.query(models.Employee).filter(
        models.Employee.employee_id == db_employee.employee_id
    ).first()
    await send_verification_email(db_employee.email, verification_token)
    return schemas.EmployeeResponse.from_orm_with_department(db_employee)
  
# HR Register
@router.post("/hr/register", response_model=schemas.HRResponse)
async def hr_register(hr: schemas.HRCreate, db: Session = Depends(get_db)):
    existing = crud.get_employee_by_email(db, hr.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    verification_token = secrets.token_urlsafe(32)
    db_hr = crud.create_hr(db, hr)
    db_hr.verification_token = verification_token
    db_hr.is_verified = False
    db.commit()
    await send_verification_email(db_hr.email, verification_token)
    return db_hr

# Verify Email
@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    employee = db.query(models.Employee).filter(
        models.Employee.verification_token == token
    ).first()
    if not employee:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    employee.is_verified = True
    employee.verification_token = None
    db.commit()
    return {"message": "Email verified successfully! You can now login."}

# Employee Login
@router.post("/login", response_model=schemas.Token)
def login(request: schemas.LoginRequest, db: Session = Depends(get_db)):
    employee = crud.get_employee_by_email(db, request.email)
    if not employee or not verify_password(request.password, employee.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if employee.role == models.RoleEnum.hr:
        raise HTTPException(status_code=403, detail="HR must use the HR login portal")
    if not employee.is_verified:
        raise HTTPException(status_code=401, detail="Please verify your email first")
    token = create_access_token({"sub": str(employee.employee_id), "role": employee.role})
    return {"access_token": token, "token_type": "bearer"}

# HR Login
@router.post("/hr/login", response_model=schemas.Token)
def hr_login(request: schemas.HRLogin, db: Session = Depends(get_db)):
    employee = crud.get_employee_by_email(db, request.email)
    if not employee or not verify_password(request.password, employee.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if employee.role != models.RoleEnum.hr:
        raise HTTPException(status_code=403, detail="Access denied! HR only")
    if not employee.is_verified:
        raise HTTPException(status_code=401, detail="Please verify your email first")
    token = create_access_token({"sub": str(employee.employee_id), "role": employee.role})
    return {"access_token": token, "token_type": "bearer"}

# Forgot Password
@router.post("/forgot-password")
async def forgot_password(email: str, db: Session = Depends(get_db)):
    employee = crud.get_employee_by_email(db, email)
    if not employee:
        raise HTTPException(status_code=404, detail="Email not found")
    reset_token = secrets.token_urlsafe(32)
    employee.reset_token = reset_token
    employee.reset_token_expires = datetime.now() + timedelta(hours=1)
    db.commit()
    await send_reset_email(employee.email, reset_token)
    return {"message": "Password reset link sent to your email!"}

# Reset Password
@router.post("/reset-password")
def reset_password(token: str, new_password: str, db: Session = Depends(get_db)):
    employee = db.query(models.Employee).filter(
        models.Employee.reset_token == token
    ).first()
    if not employee:
        raise HTTPException(status_code=400, detail="Invalid reset token")
    if employee.reset_token_expires < datetime.now():
        raise HTTPException(status_code=400, detail="Reset token has expired")
    employee.password_hash = hash_password(new_password)
    employee.reset_token = None
    employee.reset_token_expires = None
    db.commit()
    return {"message": "Password reset successfully! You can now login."}

# Change Password
@router.post("/change-password")
def change_password(old_password: str, new_password: str, db: Session = Depends(get_db)):
    return {"message": "Password changed successfully!"}