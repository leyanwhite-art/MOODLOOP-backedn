from fastapi import FastAPI
from app.routers import auth, users

app = FastAPI(
    title="MoodLoop API",
    description="HR Mental Health Monitoring System",
    version="1.0.0"
)

# Include routers
app.include_router(auth.router)
app.include_router(users.router)

@app.get("/")
def root():
    return {"message": "Welcome to MoodLoop API! 🎉"}
