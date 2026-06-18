import random
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# ⚠️ Replace with your real SendGrid API key + sender email
import os
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL = "rihamadilali1@gmail.com"

def generate_otp() -> str:
    """Generate a 6-digit OTP"""
    return str(random.randint(100000, 999999))

def send_otp_email(to_email: str, otp: str) -> bool:
    """Send OTP to given email using SendGrid"""
    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=to_email,
        subject="Your Password Reset Code",
        plain_text_content=f"Your verification code is: {otp}"
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        sg.send(message)
        return True
    except Exception as e:
        print("❌ Email sending failed:", e)
        return False
