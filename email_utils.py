import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import base64
import traceback
import sys
import os
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
    
    # Log basic info without credentials
    logger.info(f"Sending email to: {to_email}, subject: {subject}")
    
    # Build the message
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = email_from
    message["To"] = to_email
    html_part = MIMEText(html_content, "html")
    message.attach(html_part)
    
    try:
        # Create SSL context
        context = ssl.create_default_context()
        
        # Connect to the server based on SSL/TLS settings
        if use_ssl:
            server = smtplib.SMTP_SSL(email_host, email_port, context=context)
        else:
            server = smtplib.SMTP(email_host, email_port)
            if use_tls:
                server.starttls(context=context)
        
        # Standard login method
        server.login(email_user, email_password)
        
        # Send the email
        server.send_message(message)
        server.quit()
        
        logger.info(f"Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        # Log error without exposing credentials
        logger.error(f"Failed to send email: {str(e)}")
        return False

def test_password_format(email_host, email_user, email_password):
    """Test different password formats to help diagnose auth issues with PrivateEmail"""
    logger.info("\n=== Testing Password Formats ===")
    
    # Sometimes Render's environment can add unwanted whitespace or line breaks
    trimmed_password = email_password.strip()
    if trimmed_password != email_password:
        logger.info("Password had whitespace that was trimmed")
    
    # Check for common issues with special characters in passwords on Render
    if "'" in email_password or '"' in email_password:
        logger.info("Password contains quotes which may cause issues in environment variables")
    
    if "@" in email_password:
        logger.info("Password contains @ which may require URL encoding in some environments")
        
    if "&" in email_password:
        logger.info("Password contains & which may require escaping in some environments")
        
    # Some platforms have issues with very long passwords
    if len(email_password) > 50:
        logger.info(f"Password is very long ({len(email_password)} chars) which may cause issues")
    
    # Try to authenticate with SMTP directly
    try:
        logger.info("Attempting direct SMTP connection for authentication testing")
        context = ssl.create_default_context()
        
        # Try different auth methods
        smtp = smtplib.SMTP(email_host, 587, timeout=10)
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        
        # Check what authentication methods are supported
        logger.info(f"Server supports these auth methods: {smtp.esmtp_features.get('auth', 'Unknown')}")
        
        # Try login with trimmed password
        try:
            logger.info("Trying AUTH with trimmed password")
            smtp.login(email_user, trimmed_password)
            logger.info("LOGIN SUCCEEDED with trimmed password")
        except Exception as e:
            logger.error(f"Login with trimmed password failed: {e}")
            
            # Try AUTH PLAIN method
            try:
                logger.info("Trying AUTH PLAIN method directly")
                auth_string = f"\0{email_user}\0{trimmed_password}"
                auth_plain = base64.b64encode(auth_string.encode()).decode()
                smtp.docmd("AUTH", f"PLAIN {auth_plain}")
                logger.info("AUTH PLAIN SUCCEEDED")
            except Exception as e:
                logger.error(f"AUTH PLAIN failed: {e}")
            
        smtp.quit()
    except Exception as e:
        logger.error(f"Could not test auth methods: {e}")

# Add a new function to test email settings from environment directly
def print_email_config():
    """Print minimal email configuration for basic validation"""
    settings = get_settings()
    
    return {
        "host": settings.EMAIL_HOST,
        "port": settings.EMAIL_PORT,
        "user": settings.EMAIL_USER,
        "from": settings.EMAIL_FROM,
    }

# Add a direct email test function
def test_send_direct_email(to_email="test@example.com"):
    """Test sending email directly with raw SMTP commands to diagnose issues"""
    settings = get_settings()
    
    # Get email configuration
    email_host = settings.EMAIL_HOST
    email_port = settings.EMAIL_PORT
    email_user = settings.EMAIL_USER
    email_password = settings.EMAIL_PASSWORD
    
    logger.info(f"Testing direct email to {to_email}...")
    
    try:
        # Create a simple test message
        msg = MIMEMultipart()
        msg['From'] = email_user
        msg['To'] = to_email
        msg['Subject'] = "TabibMeet Email Test"
        
        body = "This is a test email to verify SMTP settings."
        msg.attach(MIMEText(body, 'plain'))
        
        # Connect to the server
        context = ssl.create_default_context()
        with smtplib.SMTP(email_host, email_port) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            
            # Try various authentication methods
            methods = [
                ("Standard login", lambda: server.login(email_user, email_password)),
                ("Trimmed password", lambda: server.login(email_user, email_password.strip())),
                # Fix the f-string with backslash issue by using string concatenation
                ("AUTH PLAIN", lambda: server.docmd("AUTH", "PLAIN " + base64.b64encode(("\0" + email_user + "\0" + email_password).encode()).decode())),
            ]
            
            success = False
            for method_name, method_func in methods:
                try:
                    logger.info(f"Trying {method_name}...")
                    method_func()
                    logger.info(f"Authentication succeeded with {method_name}")
                    success = True
                    break
                except Exception as e:
                    logger.error(f"{method_name} failed: {str(e)}")
            
            if success:
                server.send_message(msg)
                logger.info("Test email sent successfully!")
                return True
            else:
                logger.error("All authentication methods failed")
                return False
    
    except Exception as e:
        logger.error(f"Test email failed: {str(e)}")
        return False
