from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import crud, schemas, models
from app.utils.security import decode_access_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(prefix="/users", tags=["Users"])

security = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
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
    return schemas.EmployeeResponse.from_orm_with_department(current_user)


@router.get("/", response_model=list[schemas.EmployeeResponse])
def get_all_employees(db: Session = Depends(get_db), current_user: models.Employee = Depends(hr_only)):
    employees = crud.get_all_employees(db)
    return [schemas.EmployeeResponse.from_orm_with_department(e) for e in employees]


@router.get("/{employee_id}", response_model=schemas.EmployeeResponse)
def get_employee(employee_id: int, db: Session = Depends(get_db), current_user: models.Employee = Depends(hr_only)):
    employee = crud.get_employee(db, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    return schemas.EmployeeResponse.from_orm_with_department(employee) 