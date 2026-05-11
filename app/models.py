from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Enum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base
import enum


# Helper for tz-aware UTC default that matches naive DB columns
def utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Enums
class RoleEnum(str, enum.Enum):
    employee = "employee"
    manager = "manager"
    hr = "hr"


class DepartmentNameEnum(str, enum.Enum):
    accounting = "Accounting"
    maintenance = "Maintenance"
    human_resources = "Human Resources"
    it = "IT"
    sales = "Sales"
    marketing = "Marketing"


class SentimentEnum(str, enum.Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"


class EmotionEnum(str, enum.Enum):
    happiness = "happiness"
    stress = "stress"
    anger = "anger"
    motivation = "motivation"
    neutral = "neutral"
    sadness = "sadness"
    cooperation = "cooperation"


class SeverityEnum(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


# Tables
class Department(Base):
    __tablename__ = "departments"
    department_id = Column(Integer, primary_key=True, index=True)
    name = Column(Enum(DepartmentNameEnum), nullable=False, unique=True)


class Employee(Base):
    __tablename__ = "employees"
    employee_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(RoleEnum), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.department_id"), nullable=True)
    is_verified = Column(Boolean, default=False)
    verification_token = Column(String, nullable=True)
    reset_token = Column(String, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    department = relationship("Department", foreign_keys=[department_id])


class DailyReflection(Base):
    __tablename__ = "daily_reflections"
    reflection_id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.employee_id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.department_id"), nullable=False)
    input_text = Column(Text, nullable=False)
    cleaned_text = Column(Text, nullable=True)
    wellness_tip = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow_naive)


class SentimentAnalysis(Base):
    __tablename__ = "sentiment_analyses"
    analysis_id = Column(Integer, primary_key=True, index=True)
    reflection_id = Column(Integer, ForeignKey("daily_reflections.reflection_id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.department_id"), nullable=False)
    sentiment = Column(Enum(SentimentEnum), nullable=False)
    emotion = Column(Enum(EmotionEnum), nullable=False)
    confidence = Column(Float, nullable=False)
    analyzed_at = Column(DateTime, default=utcnow_naive)


class DepartmentAlarm(Base):
    __tablename__ = "department_alarms"
    alarm_id = Column(Integer, primary_key=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.department_id"), nullable=False)
    severity = Column(Enum(SeverityEnum), nullable=False)
    message = Column(Text, nullable=False)
    negative_ratio = Column(Float, nullable=False)
    analyses_count = Column(Integer, nullable=False)
    window_start = Column(DateTime, nullable=False)
    window_end = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=utcnow_naive)
    department = relationship("Department")


class CriticalKeywordAlert(Base):
    __tablename__ = "critical_keyword_alerts"
    alert_id = Column(Integer, primary_key=True, index=True)
    reflection_id = Column(Integer, ForeignKey("daily_reflections.reflection_id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.employee_id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.department_id"), nullable=True)
    matched_keyword = Column(String, nullable=False)
    snippet = Column(Text, nullable=False)
    severity = Column(Enum(SeverityEnum), nullable=False, default=SeverityEnum.critical)
    is_resolved = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=utcnow_naive)
    employee = relationship("Employee", foreign_keys=[employee_id])
    department = relationship("Department", foreign_keys=[department_id])
