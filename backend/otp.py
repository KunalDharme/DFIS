"""Email OTP delivery and verification for Pro authentication flows."""
import os
import hashlib
import secrets
import smtplib
import string
import time
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

OTP_EXPIRY_SECONDS = 300
MAX_ATTEMPTS = 5
SMTP_TIMEOUT = 15
TEMPLATES = Path(__file__).with_name("email_templates")
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                        autoescape=select_autoescape(["html", "xml"]))

VERIFICATION_TYPES = {
    "ownership": {
        "template": "dfis_ownership_verification.html",
        "subject": "DFIS | Email Ownership Verification",
        "intro": "Your DFIS email ownership verification code is",
    },
    "signup": {
        "template": "dfis_signup_verification.html",
        "subject": "DFIS Pro | Verify Your Email to Sign Up",
        "intro": "Your DFIS Pro signup verification code is",
    },
    "password_reset": {
        "template": "dfis_password_reset.html",
        "subject": "DFIS | DFIS Pro Password Reset",
        "intro": "Your DFIS Pro password reset code is",
    },
}


def generate_otp():
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))


def send_email(email, otp, verification_type):
    sender = os.getenv("DFIS_EMAIL", "").strip()
    app_password = os.getenv("DFIS_APP_PASSWORD", "").strip()
    if not sender or not app_password:
        raise ValueError("Missing DFIS_EMAIL or DFIS_APP_PASSWORD in .env")
    details = VERIFICATION_TYPES[verification_type]
    html = jinja_env.get_template(details["template"]).render(otp=otp, email=email)
    message = EmailMessage()
    message["Subject"] = details["subject"]
    message["From"] = sender
    message["To"] = email
    message.set_content(f"{details['intro']}: {otp}\n"
                        f"It expires in {OTP_EXPIRY_SECONDS // 60} minutes.\n\n"
                        "Never share this code with anyone.")
    message.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=SMTP_TIMEOUT) as server:
        server.login(sender, app_password)
        server.send_message(message)


def issue(email, verification_type):
    """Return an OTP record after delivering it to the requested email address."""
    if verification_type not in VERIFICATION_TYPES:
        raise ValueError("Unsupported verification type")
    otp = generate_otp()
    send_email(email, otp, verification_type)
    return {"digest": hashlib.sha256(otp.encode()).hexdigest(),
            "created_at": time.monotonic(), "attempts": 0,
            "dev_code": None}


def verify(record, code):
    if time.monotonic() - record["created_at"] >= OTP_EXPIRY_SECONDS:
        raise ValueError("Code expired. Request a new code.")
    if record["attempts"] >= MAX_ATTEMPTS:
        raise ValueError("Too many incorrect attempts. Request a new code.")
    record["attempts"] += 1
    digest = hashlib.sha256(code.strip().upper().encode()).hexdigest()
    if not secrets.compare_digest(record["digest"], digest):
        remaining = MAX_ATTEMPTS - record["attempts"]
        raise ValueError(f"Incorrect code. {remaining} attempts remaining." if remaining else
                         "Too many incorrect attempts. Request a new code.")
