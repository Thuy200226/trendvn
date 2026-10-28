"""Send one message through SMTP and classify the result."""
import smtplib
from email.message import EmailMessage

from . import config


def send(job):
    """Returns 'sent', 'temporary' (try later), 'permanent' (never) or 'unknown' (connection lost after the data was sent)."""
    msg = EmailMessage()
    msg["To"], msg["Subject"] = job["to_addr"], job["subject"]
    msg.set_content(job["body"])
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
            server.send_message(msg)
        return "sent"
    except smtplib.SMTPRecipientsRefused:
        return "permanent"
    except smtplib.SMTPServerDisconnected:
        return "unknown"
    except (smtplib.SMTPException, OSError):
        return "temporary"
