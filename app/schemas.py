from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from enum import Enum
from typing import Optional

# Enums
class RoleEnum(str, Enum):
    employee = "employee"
    manager = "manager"
    hr = "hr"

class DepartmentNameEnum(str, Enum):
    accounting = "Accounting"
    maintenance = "Maintenance"
    human_resources = "Human Resources"
    it = "IT"
    sales = "Sales"
    marketing = "Marketing"

class SentimentEnum(str, Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"

class EmotionEnum(str, Enum):
    happiness = "happiness"
    stress = "stress"
    anger = "anger"
    motivation = "motivation"
    neutral = "neutral"
    sadness = "sadness"
    cooperation = "cooperation"

class SeverityEnum(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

# Employee Schemas
class EmployeeCreate(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    department_name: DepartmentNameEnum

class HRCreate(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

class HRLogin(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)

class EmployeeResponse(BaseModel):
    employee_id: int
    name: str
    email: EmailStr
    role: RoleEnum
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    is_verified: bool

    @classmethod
    def from_orm_with_department(cls, employee):
        return cls(
            employee_id=employee.employee_id,
            name=employee.name,
            email=employee.email,
            role=employee.role,
            department_id=employee.department_id,
            department_name=employee.department.name if employee.department else None,
            is_verified=employee.is_verified
        )

    model_config = {"from_attributes": True}

class HRResponse(BaseModel):
    employee_id: int
    name: str
    email: EmailStr
    role: RoleEnum
    is_verified: bool

    class Config:
        from_attributes = True

# Department Schemas
class DepartmentCreate(BaseModel):
    name: str
    manager_id: Optional[int] = None

class DepartmentResponse(BaseModel):
    department_id: int
    name: str
    manager_id: Optional[int] = None

    class Config:
        from_attributes = True

class ReflectionCreate(BaseModel):
    input_text: str
    department_id: int

class ReflectionResponse(BaseModel):
    reflection_id: int
    employee_id: int
    department_id: int
    input_text: str
    cleaned_text: Optional[str] = None
    wellness_tip: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

# Sentiment Analysis Schemas
class SentimentResponse(BaseModel):
    analysis_id: int
    reflection_id: int
    department_id: int
    sentiment: SentimentEnum
    emotion: EmotionEnum
    confidence: float
    analyzed_at: datetime

    class Config:
        from_attributes = True

# Department Alarm Schemas
class AlarmResponse(BaseModel):
    alarm_id: int
    department_id: int
    severity: SeverityEnum
    message: str
    negative_ratio: float
    analyses_count: int
    window_start: datetime
    window_end: datetime
    created_at: datetime

    class Config:
        from_attributes = True

# Auth Schemas
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)

class Token(BaseModel):
    access_token: str
    token_type: str

class ChangePasswordRequest(BaseModel):
    old_password: str = Field(max_length=72)
    new_password: str = Field(min_length=8, max_length=72)

class ForgotPasswordRequest(BaseModel):
    email: EmailStr 