#!/usr/bin/env python
import os
import django
from django.core.mail import send_mail
from django.conf import settings

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Spenta.settings')
django.setup()

def test_email_sending():
    """Test if email configuration works"""
    try:
        send_mail(
            subject='Spenta CRM - Email Test',
            message='This is a test email from Spenta CRM to verify Gmail SMTP is working.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=['projects@spentacorporation.com'],  # Test with your own email
            fail_silently=False,
        )
        print("✅ Email sent successfully!")
        return True
    except Exception as e:
        print(f"❌ Email failed to send: {e}")
        return False

if __name__ == "__main__":
    test_email_sending()
