import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib

from app.config.settings import settings


def generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


async def send_verification_code(email: str, code: str):
    msg = MIMEMultipart("alternative")
    msg["From"] = settings.SMTP_USERNAME
    msg["To"] = email
    msg["Subject"] = f"【Aries Cloud】邮箱验证码 {code}"

    html = f"""
    <div style="max-width:480px;margin:0 auto;font-family:sans-serif;padding:24px;">
        <h2 style="color:#4f46e5;margin-bottom:16px;">Aries Cloud 邮箱验证</h2>
        <p style="color:#333;font-size:14px;">您正在注册 Aries Cloud 账号，验证码为：</p>
        <div style="font-size:36px;font-weight:bold;color:#4f46e5;letter-spacing:8px;margin:24px 0;text-align:center;">{code}</div>
        <p style="color:#999;font-size:12px;">验证码有效期为 {settings.CODE_EXPIRE_MINUTES} 分钟，请尽快使用。如非本人操作，请忽略此邮件。</p>
    </div>
    """
    msg.attach(MIMEText(html, "html", "utf-8"))

    await aiosmtplib.send(
        msg,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USERNAME,
        password=settings.SMTP_PASSWORD,
        start_tls=settings.SMTP_STARTTLS,
    )
