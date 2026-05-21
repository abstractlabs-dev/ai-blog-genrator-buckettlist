import os
import sys
import smtplib
import logging
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.config import Config
from src.services.email_service import EmailService

# Configure logging to stdout
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def test_real_smtp_connection():
    logger.info("Initializing diagnostic SMTP test...")
    logger.info("Configured values:")
    logger.info(f"  SMTP_HOST: {Config.SMTP_HOST}")
    logger.info(f"  SMTP_PORT: {Config.SMTP_PORT}")
    logger.info(f"  SMTP_USERNAME: {Config.SMTP_USERNAME}")
    logger.info(f"  SMTP_TO: {Config.SMTP_TO}")
    logger.info(f"  SMTP_PASSWORD exists: {bool(Config.SMTP_PASSWORD)}")

    if not Config.SMTP_PASSWORD or not Config.SMTP_USERNAME:
        logger.error("Error: SMTP_PASSWORD or SMTP_USERNAME is empty in .env!")
        return

    # Let's try raw SMTP connection first
    try:
        logger.info(f"Attempting smtplib.SMTP connection to {Config.SMTP_HOST}:{Config.SMTP_PORT}...")
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15) as server:
            logger.info("Connected successfully! Sending EHLO...")
            server.ehlo()
            
            logger.info("Attempting to start TLS...")
            server.starttls()
            server.ehlo()
            
            logger.info(f"Attempting to log in as {Config.SMTP_USERNAME}...")
            server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            logger.info("Login successful!")
            
            # Compose a test email
            logger.info("Composing a test email...")
            subject = "AI Blog Generator: SMTP Diagnostic Test"
            body = (
                "Hello,\n\n"
                "This is a diagnostic test email to verify that your SMTP credentials and "
                "network connection are working properly. If you received this, it means "
                "your SMTP setup is 100% correct!\n\n"
                "Regards,\n"
                "AI Blog Campaign Engine"
            )
            msg = f"Subject: {subject}\nFrom: {Config.SMTP_USERNAME}\nTo: {Config.SMTP_TO}\n\n{body}"
            
            logger.info(f"Sending test email to {Config.SMTP_TO}...")
            server.sendmail(Config.SMTP_USERNAME, [Config.SMTP_TO], msg)
            logger.info("✅ SMTP Diagnostic Test passed! Email sent successfully!")
            
    except Exception as e:
        logger.error("❌ SMTP Connection/Delivery failed!")
        logger.error(f"Error Details: {e}", exc_info=True)
        
        # Check for typical errors
        err_msg = str(e)
        if "Authentication failed" in err_msg or "Username and Password not accepted" in err_msg:
            logger.warning(
                "\n[POSSIBLE CAUSE] The App Password provided for Gmail might be invalid or revoked.\n"
                "Please verify that you generated a fresh 16-character 'App Password' from Google Account Settings (not your standard password)."
            )
        elif "timed out" in err_msg or "TimeoutError" in err_msg:
            logger.warning(
                "\n[POSSIBLE CAUSE] The connection timed out. This often happens if:\n"
                "1. Your ISP or network provider is blocking port 587 (very common on public/home networks).\n"
                "2. Your firewall or proxy is blocking outgoing SMTP connections."
            )
        elif "SSL" in err_msg or "STARTTLS" in err_msg:
            logger.warning(
                "\n[POSSIBLE CAUSE] SSL/TLS negotiation failed. Please check if your host uses port 465 (SMTP_PORT=465) and SMTP SSL rather than STARTTLS."
            )

if __name__ == "__main__":
    test_real_smtp_connection()
