import os
import sys
import smtplib
import ssl
import base64
import traceback
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Add the parent directory to sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Import after adding parent dir to path
from core.config import get_settings

def check_email_authentication():
    """
    Comprehensive test of email authentication using multiple methods.
    This is useful for diagnosing email issues on cloud platforms like Render.
    """
    settings = get_settings()
    
    # Get email configuration
    email_host = settings.EMAIL_HOST
    email_port = settings.EMAIL_PORT
    email_user = settings.EMAIL_USER
    email_password = settings.EMAIL_PASSWORD
    
    # Print connection details
    print("\n======= Email Authentication Test =======")
    print(f"Host: {email_host}")
    print(f"Port: {email_port}")
    print(f"User: {email_user}")
    print(f"Password length: {len(email_password) if email_password else 0}")
    print(f"Password first 3 chars: {email_password[:3] + '***' if email_password else 'None'}")
    print(f"Running on Render: {'Yes' if os.environ.get('RENDER') == 'true' else 'No'}")
    print("=========================================\n")
    
    # Try a direct connection without authentication first
    print("\n1. Testing basic connection...")
    try:
        context = ssl.create_default_context()
        if email_port == 465:
            server = smtplib.SMTP_SSL(email_host, email_port, context=context, timeout=10)
            print("   + SSL connection established successfully")
        else:
            server = smtplib.SMTP(email_host, email_port, timeout=10)
            print("   + SMTP connection established successfully")
            
            # Try STARTTLS if appropriate port
            if email_port == 587:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                print("   + STARTTLS established successfully")
        
        # Check what authentication methods are supported
        auth_methods = server.esmtp_features.get('auth', 'None reported')
        print(f"   + Server supports these AUTH methods: {auth_methods}")
        
        server.quit()
        print("   + Test connection successful\n")
    except Exception as e:
        print(f"   - Connection error: {str(e)}\n")
        print(traceback.format_exc())
        return False
    
    # Now try authentication
    print("\n2. Testing authentication with different methods...")
    
    auth_methods = [
        {
            "name": "Standard login",
            "function": lambda s: s.login(email_user, email_password),
            "description": "Standard SMTP login method"
        },
        {
            "name": "Trimmed password login",
            "function": lambda s: s.login(email_user, email_password.strip()),
            "description": "Login with whitespace trimmed from password"
        },
        {
            "name": "AUTH PLAIN",
            # Fix the f-string with backslash issue
            "function": lambda s: s.docmd("AUTH", "PLAIN " + base64.b64encode(("\0" + email_user + "\0" + email_password).encode()).decode()),
            "description": "Raw AUTH PLAIN command with base64 encoding"
        },
        {
            "name": "AUTH LOGIN",
            "function": lambda s: authenticate_login(s, email_user, email_password),
            "description": "Manual AUTH LOGIN command sequence" 
        }
    ]
    
    for method in auth_methods:
        print(f"\nTrying {method['name']}: {method['description']}")
        try:
            context = ssl.create_default_context()
            if email_port == 465:
                server = smtplib.SMTP_SSL(email_host, email_port, context=context, timeout=10)
            else:
                server = smtplib.SMTP(email_host, email_port, timeout=10)
                server.ehlo()
                if email_port == 587:
                    server.starttls(context=context)
                    server.ehlo()
            
            # Try the authentication method
            method["function"](server)
            print(f"✓ SUCCESS: {method['name']} worked!")
            
            # Try sending a test email
            print("  Testing sending an email...")
            msg = MIMEMultipart()
            msg['From'] = email_user
            msg['To'] = email_user  # Send to self for testing
            msg['Subject'] = f"TabibMeet Email Test ({method['name']})"
            body = f"This is a test email sent using {method['name']} authentication."
            msg.attach(MIMEText(body, 'plain'))
            
            try:
                server.send_message(msg)
                print(f"✓ SUCCESS: Email sent successfully using {method['name']}!")
                
                # This method works! Save the working method to a file
                with open(os.path.join(parent_dir, "email_auth_method.txt"), "w") as f:
                    f.write(method["name"])
                print(f"  Saved working method to email_auth_method.txt")
                
            except Exception as send_err:
                print(f"  × Failed to send email: {str(send_err)}")
            
            server.quit()
        except Exception as e:
            print(f"× FAILED: {method['name']} authentication failed: {str(e)}")
    
    print("\n======= Test Finished =======\n")
    return True

def authenticate_login(server, username, password):
    """Manual implementation of AUTH LOGIN sequence"""
    server.docmd("AUTH", "LOGIN")
    # Encode username in base64
    username_b64 = base64.b64encode(username.encode()).decode()
    server.docmd(username_b64)
    # Encode password in base64
    password_b64 = base64.b64encode(password.encode()).decode()
    server.docmd(password_b64)
    return True

if __name__ == "__main__":
    check_email_authentication()
