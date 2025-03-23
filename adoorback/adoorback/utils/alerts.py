import os
import traceback
from typing import Optional

import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_msg_to_slack(
    url: Optional[str] = None,
    text: Optional[str] = None,
    channel: Optional[str] = None,
    icon_emoji: Optional[str] = None,
    username: Optional[str] = None,
    level: str = "INFO",  # 👈 기본 레벨은 INFO
):
    allowed_levels = {"WARNING", "ERROR", "CRITICAL"}
    if level.upper() not in allowed_levels:
        return  # 중요하지 않은 레벨은 보내지 않음

    url = url or os.getenv("SLACK_URL")
    channel = channel or os.getenv("SLACK_CHANNEL", "8_django_alert")
    username = username or os.getenv("SLACK_USERNAME", "webhookbot")
    icon_emoji = icon_emoji or os.getenv("SLACK_ICON", ":rotating_light:")
    text = text or "Hello World!!"

    if not url:
        return

    payload = {
        "channel": channel,
        "username": username,
        "text": f"[{level.upper()}] {text}",
        "icon_emoji": icon_emoji,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception:
        traceback.print_exc()


def send_gmail_alert(
    subject: Optional[str] = None,
    body: Optional[str] = None,
    to_email: Optional[str] = None,
    from_email: Optional[str] = None,
    app_password: Optional[str] = None,
):
    subject = subject or os.getenv("GMAIL_SUBJECT", "🚨 Error Alert")
    body = body or os.getenv("GMAIL_BODY", "An error has occurred.")
    to_email = to_email or os.getenv("GMAIL_TO")
    from_email = from_email or os.getenv("GMAIL_FROM")
    app_password = app_password or os.getenv("GMAIL_APP_PASSWORD")

    if not (to_email and from_email and app_password):
        return  # 필수 정보가 없으면 전송 안 함

    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10) as server:
            server.login(from_email, app_password)
            server.send_message(msg)
    except Exception:
        traceback.print_exc()
