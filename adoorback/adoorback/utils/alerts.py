import json
import os
import traceback
from typing import Optional

import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from user_agents import parse

from adoorback.filters import get_current_request


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

    request = get_current_request()
    user_info = ""
    if request and hasattr(request, "user") and request.user.is_authenticated:
        user_info += f"\n👤 User: {request.user.username} (ID: {request.user.id})"
        token = request.META.get("HTTP_AUTHORIZATION")
        if not token and hasattr(request, "auth") and request.auth:
            token = str(request.auth)
        if token:
            user_info += f"\n🔑 Token: {token[:10]}...{token[-5:]}"

    if request:
        page = request.headers.get("X-Current-Page", "N/A")
        user_info += f"\n📄 Page: {page}"

        ua_string = request.META.get("HTTP_USER_AGENT", "")
        os_name = parse(ua_string).os.family if ua_string else "Unknown OS"
        user_info += f"\n💻 OS: {os_name}"

        try:
            if request.method in ["POST", "PUT", "PATCH"]:
                data = dict(request.data)
                sensitive_keys = ["password", "token", "secret", "registration_id"]
                for key in sensitive_keys:
                    if key in data:
                        data[key] = "[FILTERED]"
                body_str = json.dumps(data, ensure_ascii=False)
                if len(body_str) > 500:
                    body_str = body_str[:500] + " ... (truncated)"
                user_info += f"\n📦 Body: {body_str}"
        except Exception as e:
            user_info += f"\n📦 Body: [ERROR reading data: {e}]"

    url = url or os.getenv("SLACK_URL")
    channel = channel or os.getenv("SLACK_CHANNEL")
    username = username or os.getenv("SLACK_USERNAME")
    icon_emoji = icon_emoji or os.getenv("SLACK_ICON")
    text = text or "Hello World!!"

    if not url:
        return

    payload = {
        "channel": channel,
        "username": username,
        "text": f"[{level.upper()}] {text}{user_info}",
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
    request = get_current_request()
    if request and hasattr(request, "user") and request.user.is_authenticated:
        user_info = f"\n\nUser: {request.user.username} (ID: {request.user.id})"
        token = request.META.get("HTTP_AUTHORIZATION")
        if not token and hasattr(request, "auth") and request.auth:
            token = str(request.auth)
        if token:
            user_info += f"\nToken: {token[:10]}...{token[-5:]}"
        body += user_info

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
