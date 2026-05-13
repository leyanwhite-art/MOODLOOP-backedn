from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from enum import Enum
from typing import Optional, Any

# Enums
class RoleEnum(str, Enum):
    employee = "employee"
    hr = "hr"
    admin = "admin"

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
    # department_name is validated against the live Department table at use,
    # so we accept any non-empty string here rather than constraining to the
    # original fixed enum.
    name: str
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    department_name: str

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

class DepartmentResponse(BaseModel):
    department_id: int
    name: str

    class Config:
        from_attributes = True

# Reflection Schemas
class ReflectionCreate(BaseModel):
    input_text: str
    # department_id: int, not needed because reflections uses current_user.department_id
    selected_emotion: Optional[str] = None

class ReflectionResponse(BaseModel):
    reflection_id: int
    employee_id: int
    department_id: int
    input_text: str
    cleaned_text: Optional[str] = None
    wellness_tip: Optional[str] = None
    created_at: datetime
    predicted_emotion: Optional[str] = None
    confidence: Optional[float] = None

    model_config = {"from_attributes": True}

class EmotionPredictionRequest(BaseModel):
    input_text: str

class EmotionPredictionResponse(BaseModel):
    emotion: str
    intensity: float
    all_scores: dict[str, float]

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


class CriticalAlertResponse(BaseModel):
    alert_id: int
    employee_id: int
    employee_name: str
    department_id: int | None
    department_name: str | None
    matched_keyword: str
    snippet: str
    severity: SeverityEnum
    is_resolved: bool
    created_at: datetime

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

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=72)


# ── Admin Schemas ─────────────────────────────────────────────
class AdminLogin(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)


class UserAdminCreate(BaseModel):
    """Admin-side user creation. Covers employee / hr / admin via `role`."""
    name: str
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    role: RoleEnum
    department_name: Optional[str] = None


class UserAdminUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[RoleEnum] = None
    department_name: Optional[str] = None
    is_active: Optional[bool] = None


class DepartmentAdminCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class DepartmentAdminUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class DepartmentAdminView(BaseModel):
    department_id: int
    name: str
    employee_count: int

    model_config = {"from_attributes": True}


class UserAdminView(BaseModel):
    employee_id: int
    name: str
    email: EmailStr
    role: RoleEnum
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    is_active: bool
    is_verified: bool
    created_at: Optional[datetime] = None

    @classmethod
    def from_orm_with_department(cls, e):
        dept_name = None
        if e.department is not None:
            raw = e.department.name
            dept_name = raw.value if hasattr(raw, "value") else raw
        return cls(
            employee_id=e.employee_id,
            name=e.name,
            email=e.email,
            role=e.role,
            department_id=e.department_id,
            department_name=dept_name,
            is_active=bool(e.is_active),
            is_verified=bool(e.is_verified),
            created_at=e.created_at,
        )

    model_config = {"from_attributes": True}


class SettingValue(BaseModel):
    value: Any


class SettingView(BaseModel):
    key: str
    value: Any
    type: str          # "float" | "int" | "bool" | "string"
    min: Optional[float] = None
    max: Optional[float] = None
    default: Any
    description: Optional[str] = None
    updated_at: Optional[datetime] = None


class ActivityLogView(BaseModel):
    id: int
    actor_employee_id: Optional[int] = None
    actor_role: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    meta: Optional[Any] = None
    ip: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}