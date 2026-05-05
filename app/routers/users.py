from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import crud, schemas, models
from app.utils.security import decode_access_token
from fastapi.security import OAuth2PasswordBearer

router = APIRouter(prefix="/users", tags=["Users"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    employee = crud.get_employee(db, int(payload["sub"]))
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee

def hr_only(current_user: models.Employee = Depends(get_current_user)):
    if current_user.role != "hr":
        raise HTTPException(status_code=403, detail="HR access only")
    return current_user

@router.get("/me", response_model=schemas.EmployeeResponse)
def get_me(current_user: models.Employee = Depends(get_current_user)):
    return current_user

@router.get("/", response_model=list[schemas.EmployeeResponse])
def get_all_employees(db: Session = Depends(get_db), current_user: models.Employee = Depends(hr_only)):
    return crud.get_all_employees(db)

@router.get("/{employee_id}", response_model=schemas.EmployeeResponse)
def get_employee(employee_id: int, db: Session = Depends(get_db), current_user: models.Employee = Depends(hr_only)):
    employee = crud.get_employee(db, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee