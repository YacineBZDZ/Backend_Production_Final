import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import base64
import traceback
import sys
from core.config import get_settings

logger = logging.getLogger(__name__)

def add_signature_to_html(html_content: str, enabled: bool = True) -> str:
    """
    Add the TabibMeet email signature to HTML content if enabled
    
    Args:
        html_content: Original HTML content
        enabled: Whether to add signature at all
        
    Returns:
        str: HTML content with signature added
    """
    if not enabled:
        return html_content
    
    settings = get_settings()
    
    # Get signature from settings
    sig_html = settings.EMAIL_SIGNATURE_HTML
    if not sig_html:
        return html_content
    
    # Check if HTML has body tags
    if "</body>" in html_content:
        # Insert signature before closing body tag
        return html_content.replace("</body>", f"{sig_html}</body>")
    else:
        # No body tags, just append signature
        return f"{html_content}\n{sig_html}"

async def send_email(
    to_email: str, 
    subject: str, 
    html_content: str,
    signature_enabled: bool = False  # Disabled by default since we're using provider signature
) -> bool:
    """
    Send email using PrivateEmail's default signature
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML content of the email
        signature_enabled: Parameter kept for backward compatibility but ignored
        
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    settings = get_settings()
    
    # Get email configuration
    email_host = settings.EMAIL_HOST
    email_port = settings.EMAIL_PORT
    email_user = settings.EMAIL_USER
    email_password = settings.EMAIL_PASSWORD
    email_from = settings.EMAIL_FROM
    use_tls = settings.EMAIL_USE_TLS
    use_ssl = settings.EMAIL_USE_SSL
    
    # Print debug information about email configuration
    logger.info(f"Email Configuration:")
    logger.info(f"  - Host: {email_host}")
    logger.info(f"  - Port: {email_port}")
    logger.info(f"  - From: {email_from}")
    logger.info(f"  - User: {email_user}")
    logger.info(f"  - Use TLS: {use_tls}")
    logger.info(f"  - Use SSL: {use_ssl}")
    logger.info(f"  - Sending to: {to_email}")
    logger.info(f"  - Subject: {subject}")
    
    # Build the message - no custom signature needed as we're using PrivateEmail's
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = email_from
    message["To"] = to_email
    html_part = MIMEText(html_content, "html")
    message.attach(html_part)
    
    try:
        # Create SSL context
        context = ssl.create_default_context()
        logger.info(f"Created SSL context for email")
        
        # Connect to the server based on SSL/TLS settings
        if use_ssl:
            logger.info(f"Using SMTP_SSL connection to {email_host}:{email_port}")
            server = smtplib.SMTP_SSL(email_host, email_port, context=context)
        else:
            logger.info(f"Using standard SMTP connection to {email_host}:{email_port}")
            server = smtplib.SMTP(email_host, email_port)
            if use_tls:
                logger.info(f"Starting TLS for SMTP connection")
                server.starttls(context=context)
        
        # Login to the server
        logger.info(f"Attempting login with user: {email_user}")
        server.login(email_user, email_password)
        logger.info(f"Login successful")
        
        # Send the email
        logger.info(f"Sending email to {to_email}")
        server.send_message(message)
        logger.info(f"Email sent, closing connection")
        server.quit()
        
        logger.info(f"Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error(f"Failed to send email: {str(e)}")
        logger.error(f"Traceback: {error_traceback}")
        
        # Test if we can connect to the email server at all
        try:
            logger.info(f"Testing basic connection to {email_host}:{email_port}")
            if use_ssl:
                test_server = smtplib.SMTP_SSL(email_host, email_port, timeout=10)
            else:
                test_server = smtplib.SMTP(email_host, email_port, timeout=10)
            logger.info(f"Basic connection successful, can reach the server")
            test_server.quit()
        except Exception as conn_err:
            logger.error(f"Basic connection failed: {str(conn_err)}")
        
        return False

def test_password_format(email_host, email_user, email_password):
    """Test different password formats to help diagnose auth issues with PrivateEmail"""
    print("\n=== Testing Password Formats ===")
    formats = [
        ("Original", email_password),
        ("No hyphens", email_password.replace('-', '')),
        ("No special chars", ''.join(c for c in email_password if c.isalnum())),
        ("URL encoded", email_password.replace('-', '%2D'))
    ]
    
    for name, pwd in formats:
        print(f"\nTesting {name}: {'*' * len(pwd)}")
        print(f"Base64 encoded: {base64.b64encode(pwd.encode()).decode()}")
        
        # Print auth string that would be used
        auth_string = f"\0{email_user}\0{pwd}"
        auth_plain = base64.b64encode(auth_string.encode()).decode()
        print(f"AUTH PLAIN string: {auth_plain}")

# Add a new function to test email settings
def print_email_config():
    """Print all email configuration values to help with debugging"""
    settings = get_settings()
    
    # Get email configuration
    email_host = settings.EMAIL_HOST
    email_port = settings.EMAIL_PORT 
    email_user = settings.EMAIL_USER
    email_password = settings.EMAIL_PASSWORD[:3] + "***" if settings.EMAIL_PASSWORD else None
    email_from = settings.EMAIL_FROM
    use_tls = settings.EMAIL_USE_TLS
    use_ssl = settings.EMAIL_USE_SSL
    
    print("\n=== Email Configuration ===")
    print(f"Host: {email_host}")
    print(f"Port: {email_port}")
    print(f"User: {email_user}")
    print(f"Password: {email_password}")
    print(f"From: {email_from}")
    print(f"Use TLS: {use_tls}")
    print(f"Use SSL: {use_ssl}")
    print("==========================\n")
    
    return {
        "host": email_host,
        "port": email_port,
        "user": email_user,
        "from": email_from,
        "use_tls": use_tls,
        "use_ssl": use_ssl
    }
