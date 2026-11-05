import json
import os
import re
from cryptography.fernet import Fernet, InvalidToken


class Unavailable(RuntimeError):
    pass


def entitled(company_id):
    # Explicit commercial enablement; no existing subscription silently buys AI.
    return str(company_id) in {x.strip() for x in os.environ.get('AI_AUTOMATION_COMPANIES', '').split(',') if x.strip()}


def cipher():
    key = os.environ.get('AI_AUTOMATION_ENCRYPTION_KEY', '')
    if not key:
        raise Unavailable('The automation encryption key is not configured.')
    try:
        return Fernet(key.encode())
    except ValueError:
        raise Unavailable('The automation encryption key is invalid.') from None


def encrypt(values):
    return cipher().encrypt(json.dumps(values).encode()).decode()


def decrypt(value):
    if not value:
        return {}
    try:
        return json.loads(cipher().decrypt(value.encode()))
    except (InvalidToken, ValueError):
        raise Unavailable('Integration credentials cannot be decrypted.') from None


def contact(value, channel):
    value = str(value or '').strip()
    if channel == 'whatsapp':
        value = re.sub(r'[ +()\-]', '', value)
        if not re.fullmatch(r'[1-9][0-9]{7,14}', value):
            raise ValueError('Use an international phone number including the country code.')
    elif channel == 'email':
        value = value.lower()
        if len(value) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid email address.')
    else:
        raise ValueError('Unsupported communication channel.')
    return value

