from fastapi import FastAPI
from app.routers import auth, users , reflections 
from fastapi.security import HTTPBearer

security = HTTPBearer()

app = FastAPI(
    title="MoodLoop API",
    description="HR Mental Health Monitoring System",
    version="1.0.0",
    swagger_ui_init_oauth={
        "usePkceWithAuthorizationCodeGrant": True
    }
)

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(reflections.router)

@app.get("/")
def root():
    return {"message": "Welcome to MoodLoop API! 🎉"}
    