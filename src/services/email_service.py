"""
EmailService Module
===================
Handles the assembly and delivery of Sets-of-3 article emails.
Features:
- Beautiful premium HTML formatting with a modern, glassmorphism-inspired dark aesthetic.
- Attaches LinkedIn and Medium export JSON files.
- Resilient SMTP client with STARTTLS support.
- Resilient Fallback Engine: Writes complete HTML email package to disk under `data/output/emails/`
  if SMTP credentials are not configured or connection fails.
"""
import os
import json
import uuid
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from src.config import Config

logger = logging.getLogger(__name__)

class EmailService:
    """Manages email styling, packaging, and SMTP delivery or local fallback storage."""

    @staticmethod
    def _read_json_payload(path: str) -> dict:
        """Helper to read and parse local social JSON files."""
        if not path or not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as error:
            logger.error("Failed to read JSON payload at %s: %s", path, error)
            return {}

    def build_html_body(self, articles: list) -> str:
        """
        Builds a stunning, premium HSL/dark-themed HTML email presenting the set of articles,
        including visual card listings, direct copy-paste areas for LinkedIn posts, and
        Medium drafting metadata.
        """
        date_str = datetime.now().strftime("%B %d, %Y")
        
        # Build cards for each article
        cards_html = []
        for index, art in enumerate(articles, 1):
            title = art.get("title", "Untitled Article")
            wp_link = art.get("wp_link", "")
            wp_slug = art.get("wp_slug", "")
            score = art.get("score", 0)
            word_count = art.get("word_count", 0)
            art_type = art.get("type", "Generic")
            
            # Read LinkedIn JSON
            li_path = art.get("linkedin_path", "")
            li_data = self._read_json_payload(li_path)
            li_commentary = li_data.get("commentary", "LinkedIn commentary is not available.")
            
            # Read Medium JSON
            med_path = art.get("medium_path", "")
            med_data = self._read_json_payload(med_path)
            med_tags = ", ".join(med_data.get("tags", []))
            
            wp_block = ""
            if wp_link:
                wp_block = f"""
                <div style="margin-top: 10px; font-size: 13px;">
                    <strong style="color: #38bdf8;">WordPress Live URL:</strong>
                    <a href="{wp_link}" target="_blank" style="color: #38bdf8; text-decoration: none; word-break: break-all;">{wp_link}</a>
                </div>
                """
            else:
                wp_block = """
                <div style="margin-top: 10px; font-size: 13px; color: #f59e0b;">
                    <strong>WordPress URL:</strong> Not published (Generated as Draft payload)
                </div>
                """

            card = f"""
            <div class="card" style="background-color: #1e293b; border-radius: 12px; border: 1px solid #334155; padding: 25px; margin-bottom: 30px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px;">
                    <span style="background-color: #f59e0b; color: #0f172a; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 9999px; text-transform: uppercase;">Article {index}</span>
                    <span style="color: #94a3b8; font-size: 12px;">Score: <strong style="color: #34d399;">{score}/100</strong> | Word Count: <strong>{word_count}</strong></span>
                </div>
                
                <h2 style="color: #f8fafc; font-size: 20px; font-weight: 700; margin-top: 0; margin-bottom: 10px; line-height: 1.4;">{title}</h2>
                <div style="color: #94a3b8; font-size: 13px; margin-bottom: 15px;">
                    Type: <strong style="color: #f8fafc;">{art_type}</strong>
                </div>
                
                {wp_block}
                
                <hr style="border: 0; border-top: 1px solid #334155; margin: 20px 0;" />
                
                <!-- LinkedIn Box -->
                <div style="margin-bottom: 20px;">
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <span style="display: inline-block; width: 8px; height: 8px; background-color: #0077b5; border-radius: 50%; margin-right: 8px;"></span>
                        <strong style="color: #f8fafc; font-size: 14px;">LinkedIn Commentary Preview (Copy-Paste Ready)</strong>
                    </div>
                    <div style="background-color: #0f172a; border-radius: 8px; border: 1px solid #1e293b; padding: 15px; font-family: 'Courier New', Courier, monospace; font-size: 12px; color: #cbd5e1; white-space: pre-wrap; line-height: 1.5; max-height: 200px; overflow-y: auto;">{li_commentary}</div>
                </div>
                
                <!-- Medium Box -->
                <div>
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <span style="display: inline-block; width: 8px; height: 8px; background-color: #00ab6c; border-radius: 50%; margin-right: 8px;"></span>
                        <strong style="color: #f8fafc; font-size: 14px;">Medium Campaign Metadata</strong>
                    </div>
                    <div style="background-color: #0f172a; border-radius: 8px; border: 1px solid #1e293b; padding: 15px; font-size: 13px; color: #cbd5e1; line-height: 1.5;">
                        <div><strong>Suggested Tags:</strong> <span style="color: #34d399;">{med_tags or "None"}</span></div>
                        <div style="margin-top: 8px; font-size: 12px; color: #94a3b8;">
                            * The complete Medium HTML article body and publishing instructions are attached as a structured JSON file.
                        </div>
                    </div>
                </div>
            </div>
            """
            cards_html.append(card)
            
        all_cards = "\n".join(cards_html)
        
        html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Your Sets-of-3 Campaign Articles</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; color: #cbd5e1;">
    <div style="max-width: 800px; margin: 0 auto; padding: 40px 20px;">
        
        <!-- Header -->
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 30px;">
            <tr>
                <td>
                    <div style="border-bottom: 2px solid #f59e0b; padding-bottom: 20px; text-align: left;">
                        <h1 style="color: #f8fafc; font-size: 28px; font-weight: 800; margin: 0; letter-spacing: -0.025em; text-transform: uppercase;">
                            Campaign <span style="color: #f59e0b;">Social Feed</span>
                        </h1>
                        <p style="color: #94a3b8; font-size: 14px; margin: 5px 0 0 0;">
                            Auto-generated set of 3 articles ready for LinkedIn & Medium sharing | {date_str}
                        </p>
                    </div>
                </td>
            </tr>
        </table>

        <!-- Banner Summary -->
        <div style="background: linear-gradient(135deg, #1e3a8a 0%, #1e1b4b 100%); border-radius: 12px; border: 1px solid #1d4ed8; padding: 25px; margin-bottom: 30px; color: #f8fafc;">
            <h3 style="margin-top: 0; margin-bottom: 8px; font-size: 18px; font-weight: 700; color: #f59e0b;">🚀 Ready for Action!</h3>
            <p style="margin: 0; font-size: 14px; line-height: 1.6; color: #cbd5e1;">
                This premium bundle contains <strong>3 successfully generated articles</strong>. Below, you will find clean copy-paste-ready LinkedIn updates and Medium metadata. The full-structured JSONs for immediate API publishing or copy-pasting are attached directly to this email.
            </p>
        </div>

        <!-- Articles Loop -->
        {all_cards}

        <!-- Footer -->
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-top: 40px; border-top: 1px solid #334155; padding-top: 20px;">
            <tr>
                <td style="text-align: center; color: #94a3b8; font-size: 12px; line-height: 1.6;">
                    <p style="margin: 0;">
                        This email was automatically generated by the AI Blog Generator Campaign Engine.
                    </p>
                    <p style="margin: 5px 0 0 0;">
                        Sender: <strong style="color: #cbd5e1;">{Config.SMTP_USERNAME}</strong> | Recipient: <strong style="color: #cbd5e1;">{Config.SMTP_TO}</strong>
                    </p>
                    <p style="margin: 5px 0 0 0; color: #64748b;">
                        &copy; 2026 AI Blog Campaign Manager. All rights reserved.
                    </p>
                </td>
            </tr>
        </table>
        
    </div>
</body>
</html>
"""
        return html_template

    def send_articles_set(self, articles: list) -> str:
        """
        Orchestrates email composition, attaches corresponding social JSON payloads,
        attempts SMTP delivery, and defaults to local HTML storage fallback on error/no credentials.

        Returns:
            ``"sent"``     – email was accepted by the remote SMTP server.
            ``"fallback"`` – SMTP unavailable/failed; HTML package saved locally to disk.
            ``"failed"``   – no articles provided; nothing was done.
        """
        if not articles:
            logger.warning("No articles provided to send_articles_set. Skipping.")
            return "failed"
            
        logger.info("Assembling email body and attachments for a set of %d articles...", len(articles))
        
        # 1. Build beautiful HTML
        html_body = self.build_html_body(articles)
        
        # Generate a unique timestamp + UUID identifier for local files or references
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:8]
        
        # 2. Check if SMTP configuration is present
        # In a real environment, we'd check if SMTP_PASSWORD is not empty.
        is_smtp_available = bool(Config.SMTP_PASSWORD and Config.SMTP_USERNAME)
        
        if is_smtp_available:
            try:
                logger.info("Configured SMTP credentials found. Attempting SMTP delivery via %s:%s...", Config.SMTP_HOST, Config.SMTP_PORT)
                
                # Assemble MIMEMultipart email
                msg = MIMEMultipart()
                msg["Subject"] = f"🚀 AI Blog Campaign: New Set of {len(articles)} Articles ready for Publishing"
                msg["From"] = Config.SMTP_USERNAME
                msg["To"] = Config.SMTP_TO
                
                # Attach HTML
                msg.attach(MIMEText(html_body, "html"))
                
                # Attach social JSON files
                for idx, art in enumerate(articles, 1):
                    # Attach LinkedIn JSON
                    li_path = art.get("linkedin_path", "")
                    if li_path and os.path.exists(li_path):
                        filename = os.path.basename(li_path)
                        try:
                            with open(li_path, "rb") as fh:
                                part = MIMEApplication(fh.read(), Name=filename)
                            part['Content-Disposition'] = f'attachment; filename="{filename}"'
                            msg.attach(part)
                            logger.info("Attached LinkedIn JSON: %s", filename)
                        except Exception as attachment_err:
                            logger.error("Failed to attach LinkedIn JSON %s: %s", li_path, attachment_err)
                            
                    # Attach Medium JSON
                    med_path = art.get("medium_path", "")
                    if med_path and os.path.exists(med_path):
                        filename = os.path.basename(med_path)
                        try:
                            with open(med_path, "rb") as fh:
                                part = MIMEApplication(fh.read(), Name=filename)
                            part['Content-Disposition'] = f'attachment; filename="{filename}"'
                            msg.attach(part)
                            logger.info("Attached Medium JSON: %s", filename)
                        except Exception as attachment_err:
                            logger.error("Failed to attach Medium JSON %s: %s", med_path, attachment_err)

                # Connect and send
                with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
                    server.sendmail(Config.SMTP_USERNAME, [Config.SMTP_TO], msg.as_string())
                    
                logger.info("Successfully sent sets-of-3 article email from %s to %s via SMTP!", Config.SMTP_USERNAME, Config.SMTP_TO)
                return "sent"
                
            except Exception as smtp_error:
                print(f"\n[ERROR] SMTP delivery failed! Error: {smtp_error}")
                print("[WARNING] Initiating local fallback storage...")
                logger.error("SMTP delivery failed with error: %s. Initiating local fallback engine...", smtp_error)
        else:
            print("\n[WARNING] SMTP configuration missing in .env! Emails will NOT be sent via network.")
            print("[WARNING] Initiating local fallback storage...")
            logger.warning("SMTP_PASSWORD or SMTP_USERNAME not configured in .env. Initiating local fallback engine...")
            
        # 3. Fallback Engine: Save local copy to data/output/emails/
        fallback_filename = f"failed_email_set_{timestamp}_{uid}.html"
        fallback_path = os.path.join(Config.EMAILS_DIR, fallback_filename)
        
        try:
            # Let's ensure directory is created
            Config.ensure_directories()
            with open(fallback_path, "w", encoding="utf-8") as fh:
                fh.write(html_body)
                
            print(f"\n[FALLBACK SUCCESS] Saved campaign review email locally to: {fallback_path}")
            logger.info("Fallback engine successfully saved HTML email content locally: %s", fallback_path)
            return "fallback"
        except Exception as fallback_error:
            logger.critical("Fallback engine failed to write HTML email to disk: %s", fallback_error)
            return "failed"
