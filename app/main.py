from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.routers import auth, users, reflections, alarms, hr, admin
from app.database import SessionLocal
from app.utils.alarm import run_daily_alarm_check
from app.routers.admin import enforce_retention
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import traceback
import logging
import os

scheduler = BackgroundScheduler()

def alarm_job():
    db = SessionLocal()
    try:
        run_daily_alarm_check(db)
    finally:
        db.close()

def retention_job():
    db = SessionLocal()
    try:
        n = enforce_retention(db)
        print(f"🧹 Retention job purged {n} reflections")
    finally:
        db.close()

scheduler.add_job(
    alarm_job,
    CronTrigger(hour=12, minute=0),
    id="daily_alarm_check",
    replace_existing=True
)
scheduler.add_job(
    retention_job,
    CronTrigger(hour=3, minute=0),
    id="daily_retention",
    replace_existing=True
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    print("Scheduler started")
    yield
    scheduler.shutdown()

app = FastAPI(
    title="MoodLoop API",
    description="HR Mental Health Monitoring System",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        os.environ.get("FRONTEND_URL"),
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

logger = logging.getLogger("moodloop")


# Registered as an exception handler (not HTTP middleware) so it runs *inside*
# the CORS middleware. Returning a JSONResponse from an outer middleware skips
# CORS's response phase and the browser then reports the 500 as a CORS failure.
@app.exception_handler(Exception)
async def catch_unhandled_exceptions(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(reflections.router)
app.include_router(alarms.router)
app.include_router(hr.router)
app.include_router(admin.router)

@app.get("/")
def root():
    return {"message": "Welcome to MoodLoop API!"}
