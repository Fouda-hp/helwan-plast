"""
auth_email.py - إرسال البريد (Gmail API، الموافقة/الرفض)
"""

import logging
logger = logging.getLogger(__name__)

try:
    import anvil.email
    EMAIL_SERVICE_AVAILABLE = True
except ImportError:
    EMAIL_SERVICE_AVAILABLE = False

try:
    import anvil.google.mail as _gmail
    _GMAIL_AVAILABLE = True
except ImportError:
    _GMAIL_AVAILABLE = False


def send_email_smtp(to_email, subject, html_body):
    if not _GMAIL_AVAILABLE:
        logger.error("anvil.google.mail not available")
        return False
    try:
        logger.info("Attempting to send email via Google to %s", to_email)
        _gmail.send(to=to_email, subject=subject, html=html_body)
        logger.info("Email sent successfully via Google to %s", to_email)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s: %s", to_email, type(e).__name__, e)
        return False


def send_approval_email(user_email, user_name, role, approved=True):
    if not EMAIL_SERVICE_AVAILABLE:
        logger.warning("Email service not available. Skipping email notification.")
        return False
    try:
        if approved:
            subject = "Account Approved - Helwan Plast System"
            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0; text-align: center;">Helwan Plast System</h1>
                </div>
                <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #2e7d32; margin-top: 0;">Account Approved!</h2>
                    <p style="font-size: 16px; color: #333;">Dear <strong>{user_name}</strong>,</p>
                    <p style="font-size: 16px; color: #333;">Your account has been approved! You can now log in to the Helwan Plast System.</p>
                    <div style="background: #e8f5e9; padding: 15px; border-radius: 8px; margin: 20px 0;">
                        <p style="margin: 0; font-size: 14px; color: #2e7d32;"><strong>Your Role:</strong> {role.capitalize()}</p>
                    </div>
                    <p style="font-size: 12px; color: #999; text-align: center;">Best regards,<br><strong>Helwan Plast</strong></p>
                </div>
            </div>
            """
        else:
            subject = "Account Status Update - Helwan Plast System"
            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0; text-align: center;">Helwan Plast System</h1>
                </div>
                <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #c62828; margin-top: 0;">Account Registration Status</h2>
                    <p style="font-size: 16px; color: #333;">Dear <strong>{user_name}</strong>,</p>
                    <p style="font-size: 16px; color: #333;">We regret to inform you that your account registration request has been declined.</p>
                    <p style="font-size: 12px; color: #999; text-align: center;">Best regards,<br><strong>Helwan Plast</strong></p>
                </div>
            </div>
            """
        return send_email_smtp(user_email, subject, html_body)
    except Exception as e:
        logger.error("Failed to send email to %s: %s", user_email, e)
        return False
