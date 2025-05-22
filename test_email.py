import asyncio
import logging
from core.config import get_settings
from email_utils import send_email

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

async def test_email():
    """Simple utility to test email sending"""
    settings = get_settings()
    
    # Test email parameters
    to_email = input("Enter test email recipient: ") or "test@example.com"
    subject = "Test Email - TabibMeet API"
    html_content = """
    <html>
    <body>
        <h2>Email Test</h2>
        <p>This is a test email from the TabibMeet API.</p>
        <p>If you're seeing this, email sending is working correctly!</p>
    </body>
    </html>
    """
    
    logger.info(f"Sending test email to {to_email}...")
    result = await send_email(to_email, subject, html_content, signature_enabled=True)
    
    if result:
        logger.info("✅ Email sent successfully!")
    else:
        logger.error("❌ Failed to send email.")

if __name__ == "__main__":
    asyncio.run(test_email())
