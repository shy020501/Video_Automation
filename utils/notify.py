import smtplib
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_crash_email(
    subject: str,
    body: str,
    to_email: str,
    from_email: str,
    app_password: str,
):
    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_email, app_password)
        server.send_message(msg)

def notify_crash(
    exc: Exception,
    context: dict,
    to_email: str,
    from_email: str,
    app_password: str,
):
    tb = traceback.format_exc()

    body = f"""
[CRASH DETECTED]

Exception:
{repr(exc)}

Context:
{context}

Traceback:
{tb}
"""

    send_crash_email(
        subject="[AI Posts] Crash detected",
        body=body,
        to_email=to_email,
        from_email=from_email,
        app_password=app_password,
    )
