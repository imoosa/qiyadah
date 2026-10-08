"""Authentication helpers supporting existing accounts and secure new passwords."""
import hashlib
import hmac
from werkzeug.security import generate_password_hash, check_password_hash


def hash_password(password):
    return generate_password_hash(password)


def verify_password(password, hashed):
    if not hashed:
        return False
    if len(hashed) == 64 and all(c in '0123456789abcdef' for c in hashed.lower()):
        return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), hashed.lower())
    try:
        return check_password_hash(hashed, password)
    except (ValueError, TypeError):
        return False
