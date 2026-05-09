from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from app.routers import auth, users, reflections, alarms
from app.database import SessionLocal
from app.utils.alarm import run_daily_alarm_check
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import traceback

# Scheduler setup
scheduler = BackgroundScheduler()

def alarm_job():
    db = SessionLocal()
    try:
        run_daily_alarm_check(db)
    finally:
        db.close()

# Run every day at 12:00 PM
scheduler.add_job(
    alarm_job,
    CronTrigger(hour=12, minute=0),
    id="daily_alarm_check",
    replace_existing=True
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler.start()
    print("✅ Scheduler started - alarm check runs daily at 12:00 PM")
    yield
    # Shutdown
    scheduler.shutdown()
    print("Scheduler stopped")

app = FastAPI(
    title="MoodLoop API",
    description="HR Mental Health Monitoring System",
    version="1.0.0",
    lifespan=lifespan
)

@app.middleware("http")
async def catch_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": str(e)})

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(reflections.router)
app.include_router(alarms.router)

@app.get("/")
def root():
    return {"message": "Welcome to MoodLoop API! 🎉"} 