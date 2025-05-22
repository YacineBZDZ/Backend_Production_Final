import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import getpass
import sys
import base64

def test_email_connection(
    host=None, 
    port=None, 
    user=None, 
    password=None, 
    use_tls=True,
    to_email=None,
    verbose=True
):
    """Test SMTP connection with given credentials"""
    
    # Use provided values or prompt for them
    host = host or input("Enter SMTP server (e.g., mail.privateemail.com): ")
    port = port or int(input("Enter SMTP port (e.g., 587 for TLS, 465 for SSL): "))
    user = user or input("Enter email username: ")
    password = password or getpass.getpass("Enter email password: ")
    to_email = to_email or input("Enter recipient email for testing: ")
    
    if verbose:
        print(f"\nTesting connection to {host}:{port}")
        print(f"Username: {user}")
        print(f"Password: {'*' * len(password)}")
        print(f"TLS enabled: {use_tls}")
        print(f"Test recipient: {to_email}")
    
    # Create message
    message = MIMEMultipart()
    message["From"] = user
    message["To"] = to_email
    message["Subject"] = "TabibMeet Test Email"
    
    body = """
    This is a test email from TabibMeet.
    If you're seeing this, the email configuration is working!
    """
    message.attach(MIMEText(body, "plain"))
    
    # Connection details for debugging
    if verbose:
        print("\n--- Connection Details ---")
        print(f"Connecting to: {host}:{port}")
        print(f"Using TLS: {use_tls}")
        print(f"From: {user}")
        print("-------------------------")
    
    try:
        # Try with standard TLS connection first
        if use_tls:
            if verbose:
                print("\nTrying STARTTLS connection...")
            server = smtplib.SMTP(host, port)
            server.set_debuglevel(1 if verbose else 0)
            server.ehlo()
            server.starttls()
            server.ehlo()
            
            # Try AUTH PLAIN
            if verbose:
                print("\nTrying AUTH PLAIN...")
            auth_string = f"\0{user}\0{password}"
            auth_b64 = base64.b64encode(auth_string.encode()).decode()
            try:
                code, response = server.docmd("AUTH", f"PLAIN {auth_b64}")
                if verbose:
                    print(f"Response: {code} {response}")
                if code != 235:  # 235 is success code
                    raise smtplib.SMTPAuthenticationError(code, response)
            except smtplib.SMTPAuthenticationError as e:
                if verbose:
                    print(f"AUTH PLAIN failed: {e}")
                
                # Fall back to standard login
                if verbose:
                    print("\nFalling back to standard login...")
                server.login(user, password)
            
            server.sendmail(user, to_email, message.as_string())
            if verbose:
                print("\n✅ Test email sent successfully using STARTTLS!")
            server.quit()
            return True
        
        # If TLS didn't work, try direct SSL
        else:
            if verbose:
                print("\nTrying direct SSL connection...")
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(host, port, context=context)
            server.set_debuglevel(1 if verbose else 0)
            server.login(user, password)
            server.sendmail(user, to_email, message.as_string())
            if verbose:
                print("\n✅ Test email sent successfully using SSL!")
            server.quit()
            return True
        
    except Exception as e:
        if verbose:
            print(f"\n❌ Error: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            print(f"Traceback: {sys.exc_info()}")
        
        # If TLS failed, try direct SSL as fallback
        if use_tls:
            if verbose:
                print("\nTrying fallback to direct SSL connection...")
            try:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(host, 465, context=context)
                server.set_debuglevel(1 if verbose else 0)
                server.login(user, password)
                server.sendmail(user, to_email, message.as_string())
                if verbose:
                    print("\n✅ Test email sent successfully using SSL fallback!")
                server.quit()
                return True
            except Exception as e2:
                if verbose:
                    print(f"\n❌ SSL fallback also failed: {str(e2)}")
                return False
        return False

if __name__ == "__main__":
    # Get settings from environment or input
    from core.config import get_settings
    
    settings = get_settings()
    print("\n=== Testing Email Configuration ===")
    
    # Try with current settings first
    print("\nTesting with current environment settings...")
    success = test_email_connection(
        host=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        user=settings.EMAIL_USER,
        password=settings.EMAIL_PASSWORD,
        use_tls=settings.EMAIL_USE_TLS
    )
    
    if not success:
        print("\n❌ Current settings failed.")
        
        # Try alternative settings
        print("\nWould you like to try with Gmail instead? (y/n)")
        if input().lower() == 'y':
            gmail_user = input("Enter Gmail address: ")
            gmail_pass = getpass.getpass("Enter Gmail app password: ")
            
            print("\nTesting with Gmail...")
            success = test_email_connection(
                host="smtp.gmail.com",
                port=587,
                user=gmail_user,
                password=gmail_pass,
                use_tls=True
            )
            
            if success:
                print("\n✅ Gmail test successful!")
                print("\nUpdate your .env file with these settings:")
                print("EMAIL_HOST=smtp.gmail.com")
                print("EMAIL_PORT=587")
                print(f"EMAIL_USER={gmail_user}")
                print(f"EMAIL_FROM={gmail_user}")
                print("EMAIL_PASSWORD=<your-app-password>")
                print("EMAIL_USE_TLS=True")
        
        if not success:
            print("\nWould you like to manually enter SMTP details? (y/n)")
            if input().lower() == 'y':
                test_email_connection()
    else:
        print("\n✅ Current email settings are working correctly!")
