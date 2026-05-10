from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/moodloop_db"
    SECRET_KEY: str = "moodloop-secret-key-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480 
    MAIL_USERNAME: str = "test@gmail.com"
    MAIL_PASSWORD: str = "testpassword"
    MAIL_FROM: str = "test@gmail.com"
    MAIL_PORT: int = 587
    MAIL_SERVER: str = "smtp.gmail.com"

    model_config = {
        "extra": "ignore"
    }

settings = Settings()