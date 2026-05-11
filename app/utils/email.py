from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.config import settings

conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True
)


async def send_verification_email(email: str, token: str):
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    message = MessageSchema(
        subject="Verify your MoodLoop account",
        recipients=[email],
        body=f"""
        <h2>Welcome to MoodLoop!</h2>
        <p>Please verify your email by clicking the link below:</p>
        <a href="{link}">Verify Email</a>
        <p>This link expires in 24 hours.</p>
        """,
        subtype="html"
    )
    fm = FastMail(conf)
    await fm.send_message(message)


async def send_reset_email(email: str, token: str):
    link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    message = MessageSchema(
        subject="Reset your MoodLoop password",
        recipients=[email],
        body=f"""
        <h2>Password Reset Request 🔒</h2>
        <p>Click the link below to reset your password:</p>
        <a href="{link}">Reset Password</a>
        <p>This link expires in 1 hour.</p>
        <p>If you didn't request this, ignore this email.</p>
        """,
        subtype="html"
    )
    fm = FastMail(conf)
    await fm.send_message(message) 