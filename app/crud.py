from sqlalchemy.orm import Session
from app import models, schemas
from app.utils.security import hash_password
from fastapi import HTTPException

# Employee CRUD
def get_employee(db: Session, employee_id: int):
    return db.query(models.Employee).filter(models.Employee.employee_id == employee_id).first()

def get_employee_by_email(db: Session, email: str):
    return db.query(models.Employee).filter(models.Employee.email == email).first()

def get_all_employees(db: Session):
    return db.query(models.Employee).all()

def create_employee(db: Session, employee: schemas.EmployeeCreate):
    # Find department by name
    department = db.query(models.Department).filter(
        models.Department.name == employee.department_name
    ).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")
    hashed_password = hash_password(employee.password)
    db_employee = models.Employee(
        name=employee.name,
        email=employee.email,
        password_hash=hashed_password,
        role=models.RoleEnum.employee,
        department_id=department.department_id
    )
    db.add(db_employee)
    db.commit()
    db.refresh(db_employee)
    return db_employee

def create_hr(db: Session, hr: schemas.HRCreate):
    hashed_password = hash_password(hr.password)
    db_hr = models.Employee(
        name=hr.name,
        email=hr.email,
        password_hash=hashed_password,
        role=models.RoleEnum.hr,
        department_id=None
    )
    db.add(db_hr)
    db.commit()
    db.refresh(db_hr)
    return db_hr

# Department CRUD
def get_department(db: Session, department_id: int):
    return db.query(models.Department).filter(models.Department.department_id == department_id).first()

def get_all_departments(db: Session):
    return db.query(models.Department).all()

def create_department(db: Session, department: schemas.DepartmentCreate):
    db_department = models.Department(name=department.name)
    db.add(db_department)
    db.commit()
    db.refresh(db_department)
    return db_department 

# Daily Reflection CRUD
def create_reflection(db: Session, reflection: schemas.ReflectionCreate, employee_id: int):
    db_reflection = models.DailyReflection(
        employee_id=employee_id,
        department_id=reflection.department_id,
        input_text=reflection.input_text
    )
    db.add(db_reflection)
    db.commit()
    db.refresh(db_reflection)
    return db_reflection

def get_reflections_by_employee(db: Session, employee_id: int):
    return db.query(models.DailyReflection).filter(models.DailyReflection.employee_id == employee_id).all()

def get_reflections_by_department(db: Session, department_id: int):
    return db.query(models.DailyReflection).filter(models.DailyReflection.department_id == department_id).all()

# Sentiment Analysis CRUD
def create_sentiment(db: Session, reflection_id: int, department_id: int, sentiment: str, emotion: str, confidence: float):
    db_sentiment = models.SentimentAnalysis(
        reflection_id=reflection_id,
        department_id=department_id,
        sentiment=sentiment,
        emotion=emotion,
        confidence=confidence
    )
    db.add(db_sentiment)
    db.commit()
    db.refresh(db_sentiment)
    return db_sentiment

def get_sentiments_by_department(db: Session, department_id: int):
    return db.query(models.SentimentAnalysis).filter(models.SentimentAnalysis.department_id == department_id).all()

# Department Alarm CRUD
def create_alarm(db: Session, alarm_data: dict):
    db_alarm = models.DepartmentAlarm(**alarm_data)
    db.add(db_alarm)
    db.commit()
    db.refresh(db_alarm)
    return db_alarm

def get_alarms_by_department(db: Session, department_id: int):
    return db.query(models.DepartmentAlarm).filter(models.DepartmentAlarm.department_id == department_id).all()