from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app import crud, schemas, models
from app.utils.security import verify_password, create_access_token, hash_password, hash_token
from app.utils.audit import log_action
from app.routers.users import get_current_user
from app.utils.email import send_verification_email, send_reset_email
import secrets
from datetime import datetime, timedelta, timezone

router = APIRouter(prefix="/auth", tags=["Auth"])


def _check_login_preconditions(employee: models.Employee | None, password: str, *, expected_role: str, db: Session, request: Request, email: str):
    """Common login checks. Audits failures and raises the right HTTPException."""
    if not employee or not verify_password(password, employee.password_hash):
        log_action(db, request, None, "login.failure", meta={"email": email, "reason": "credentials"})
        raise HTTPException(status_code=401, detail="Invalid email or password")
    role_val = employee.role.value if hasattr(employee.role, "value") else employee.role
    if expected_role == "employee" and role_val == "hr":
        raise HTTPException(status_code=403, detail="HR must use the HR login portal")
    if expected_role == "employee" and role_val == "admin":
        raise HTTPException(status_code=403, detail="Admins must use the admin login portal")
    if expected_role == "hr" and role_val != "hr":
        raise HTTPException(status_code=403, detail="Access denied! HR only")
    if expected_role == "admin" and role_val != "admin":
        raise HTTPException(status_code=403, detail="Access denied! Admin only")
    if not employee.is_verified:
        raise HTTPException(status_code=401, detail="Please verify your email first")
    if not employee.is_active:
        log_action(db, request, employee, "login.failure", meta={"email": email, "reason": "inactive"})
        raise HTTPException(status_code=403, detail="Account has been deactivated. Contact your administrator.")


# Employee Register
@router.post("/register", response_model=schemas.EmployeeResponse)
async def register(employee: schemas.EmployeeCreate, request: Request, db: Session = Depends(get_db)):
    existing = crud.get_employee_by_email(db, employee.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    verification_token = secrets.token_urlsafe(32)
    db_employee = crud.create_employee(db, employee)
    # Store only the hash; email the raw token to the user
    db_employee.verification_token = hash_token(verification_token)
    db_employee.is_verified = False
    db.commit()
    db.refresh(db_employee)
    db_employee = db.query(models.Employee).filter(
        models.Employee.employee_id == db_employee.employee_id
    ).first()
    log_action(db, request, None, "user.register", target_type="employee", target_id=db_employee.employee_id, meta={"role": "employee"})
    await send_verification_email(db_employee.email, verification_token)
    return schemas.EmployeeResponse.from_orm_with_department(db_employee)


# HR Register
@router.post("/hr/register", response_model=schemas.HRResponse)
async def hr_register(hr: schemas.HRCreate, request: Request, db: Session = Depends(get_db)):
    existing = crud.get_employee_by_email(db, hr.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    verification_token = secrets.token_urlsafe(32)
    db_hr = crud.create_hr(db, hr)
    db_hr.verification_token = hash_token(verification_token)
    db_hr.is_verified = False
    db.commit()
    log_action(db, request, None, "user.register", target_type="employee", target_id=db_hr.employee_id, meta={"role": "hr"})
    await send_verification_email(db_hr.email, verification_token)
    return db_hr


# Verify Email
@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    # Hash the incoming token to compare against the stored hash
    hashed = hash_token(token)
    employee = db.query(models.Employee).filter(
        models.Employee.verification_token == hashed
    ).first()
    if not employee:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    employee.is_verified = True
    employee.verification_token = None
    db.commit()
    return {"message": "Email verified successfully! You can now login."}


# Employee Login
@router.post("/login", response_model=schemas.Token)
def login(request_payload: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    employee = crud.get_employee_by_email(db, request_payload.email)
    _check_login_preconditions(employee, request_payload.password, expected_role="employee", db=db, request=request, email=request_payload.email)
    token = create_access_token({"sub": str(employee.employee_id), "role": employee.role.value if hasattr(employee.role, "value") else employee.role})
    log_action(db, request, employee, "login.success", target_type="employee", target_id=employee.employee_id, meta={"role": "employee"})
    return {"access_token": token, "token_type": "bearer"}


# HR Login
@router.post("/hr/login", response_model=schemas.Token)
def hr_login(request_payload: schemas.HRLogin, request: Request, db: Session = Depends(get_db)):
    employee = crud.get_employee_by_email(db, request_payload.email)
    _check_login_preconditions(employee, request_payload.password, expected_role="hr", db=db, request=request, email=request_payload.email)
    token = create_access_token({"sub": str(employee.employee_id), "role": employee.role.value if hasattr(employee.role, "value") else employee.role})
    log_action(db, request, employee, "login.success", target_type="employee", target_id=employee.employee_id, meta={"role": "hr"})
    return {"access_token": token, "token_type": "bearer"}


# Admin Login
@router.post("/admin/login", response_model=schemas.Token)
def admin_login(request_payload: schemas.AdminLogin, request: Request, db: Session = Depends(get_db)):
    employee = crud.get_employee_by_email(db, request_payload.email)
    _check_login_preconditions(employee, request_payload.password, expected_role="admin", db=db, request=request, email=request_payload.email)
    token = create_access_token({"sub": str(employee.employee_id), "role": employee.role.value if hasattr(employee.role, "value") else employee.role})
    log_action(db, request, employee, "login.success", target_type="employee", target_id=employee.employee_id, meta={"role": "admin"})
    return {"access_token": token, "token_type": "bearer"}


# Forgot Password
@router.post("/forgot-password")
async def forgot_password(
    request_payload: schemas.ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    # Generic response — same whether the email exists or not (prevents enumeration)
    generic_response = {"message": "If that email is registered, a password reset link has been sent."}

    employee = crud.get_employee_by_email(db, request_payload.email)
    if not employee:
        return generic_response

    # Email exists — generate token, store its hash, email the raw value
    reset_token = secrets.token_urlsafe(32)
    employee.reset_token = hash_token(reset_token)
    employee.reset_token_expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    db.commit()

    try:
        await send_reset_email(employee.email, reset_token)
    except Exception as e:
        print(f"Failed to send reset email to {employee.email}: {e}")

    return generic_response


# Reset Password
# Reset Password
@router.post("/reset-password")
def reset_password(
    payload: schemas.ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    # Hash the incoming token to compare against the stored hash
    hashed = hash_token(payload.token)
    employee = db.query(models.Employee).filter(
        models.Employee.reset_token == hashed
    ).first()
    if not employee:
        raise HTTPException(status_code=400, detail="Invalid reset token")
    if not employee.reset_token_expires or employee.reset_token_expires < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="Reset token has expired")
    employee.password_hash = hash_password(payload.new_password)


# Change Password
@router.post("/change-password")
def change_password(
    request_payload: schemas.ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(get_current_user)
):
    if not verify_password(request_payload.old_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    if request_payload.old_password == request_payload.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")

    current_user.password_hash = hash_password(request_payload.new_password)
    db.commit()
    log_action(db, request, current_user, "password.change", target_type="employee", target_id=current_user.employee_id)

    return {"message": "Password changed successfully"}
