import smtplib
import ssl
import os
from email.message import EmailMessage
from ..config import Unavailable
from .whatsapp_service import DeliveryUnknown


def send(config, secrets, recipient, payload, message_id):
    # SMTP hosts are deployment-controlled, preventing server-side requests to
    # arbitrary internal endpoints through a tenant's integration form.
    host = config.get('host', '')
    allowed = {h.strip() for h in os.environ.get('AI_SMTP_ALLOWED_HOSTS', '').split(',') if h.strip()}
    if host not in allowed:
        raise Unavailable('The SMTP host has not been allowed by the platform operator.')
    message = EmailMessage()
    message['From'] = config['sender']
    message['To'] = recipient
    message['Subject'] = 'Qiyadah business update'
    message['Message-ID'] = f'<qiyadah-{message_id}@{config["sender"].split("@")[-1]}>'
    message.set_content(payload['text'])
    try:
        with smtplib.SMTP_SSL(host, 465, timeout=20, context=ssl.create_default_context()) as smtp:
            smtp.login(secrets['username'], secrets['password'])
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        raise DeliveryUnknown('Email delivery is unconfirmed. Check the provider before retrying.') from None
    return str(message['Message-ID'])
