import os
import smtplib

from email.message import EmailMessage


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_alert_email(
    severity: str,
    incident_id: str,
    service: str,
    reason: str,
):
    sender = os.getenv("CICADA_EMAIL_SENDER")
    password = os.getenv("CICADA_EMAIL_PASSWORD")
    recipient = os.getenv("CICADA_ALERT_RECIPIENT")

    if not all([sender, password, recipient]):
        raise RuntimeError("Email notification environment variables are missing")

    if severity.upper() not in {"CRITICAL", "HIGH"}:
        return {
            "status": "skipped",
            "reason": "Severity does not require email notification",
        }

    message = EmailMessage()

    message["Subject"] = f"[CICADA] {severity.upper()} Incident Detected"
    message["From"] = sender
    message["To"] = recipient

    message.set_content(
        f"""
CICADA SECURE AIOPS ALERT

Incident ID: {incident_id}
Service: {service}
Severity: {severity.upper()}

Reason:
{reason}

Action Required:
Investigate the affected service.

This is an automated notification from CICADA.
"""
    )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(message)

    return {
        "status": "sent",
        "recipient": recipient,
        "severity": severity.upper(),
        "incident_id": incident_id,
    }