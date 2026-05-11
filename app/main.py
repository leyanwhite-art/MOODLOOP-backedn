from fastapi import FastAPI, Request , HTTPException 
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.routers import auth, users, reflections, alarms, hr
from app.database import SessionLocal
from app.utils.alarm import run_daily_alarm_check
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import traceback
import logging

scheduler = BackgroundScheduler()

def alarm_job():
    db = SessionLocal()
    try:
        run_daily_alarm_check(db)
    finally:
        db.close()

scheduler.add_job(
    alarm_job,
    CronTrigger(hour=12, minute=0),
    id="daily_alarm_check",
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
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
) 

logger = logging.getLogger("moodloop")


@app.middleware("http")
async def catch_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except HTTPException:
        # Let FastAPI handle its own intentional exceptions normally
        raise
    except Exception:
        # Log full details server-side, return generic message to client
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

@app.get("/")
def root():
    return {"message": "Welcome to MoodLoop API!"}