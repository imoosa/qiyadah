"""Database-backed verification challenges and shared authentication limits."""
import hashlib
import hmac
import secrets
import time
from flask import current_app
from sqlalchemy.exc import IntegrityError
from platform_models import db


class VerificationChallenge(db.Model):
    __tablename__ = 'verification_challenges'
    id = db.Column(db.String(64), primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    digest = db.Column(db.String(64), nullable=False)
    expires = db.Column(db.BigInteger, nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    consumed = db.Column(db.Boolean, nullable=False, default=False)


class AuthenticationLimit(db.Model):
    __tablename__ = 'authentication_limits'
    key = db.Column(db.String(64), primary_key=True)
    count = db.Column(db.Integer, nullable=False)
    expires = db.Column(db.BigInteger, nullable=False)


def allow_attempt(scope, subject, limit, window, now=None):
    """Atomic fixed-window counter, shared by all web workers in the platform DB.

    Call outside business transactions: this deliberately commits its own counter.
    """
    redis_service = current_app.extensions.get('redis_service')
    if redis_service and redis_service.rate_limits_enabled:
        return redis_service.allow_attempt(scope, subject, limit, window, now=now)
    now = int(time.time() if now is None else now)
    bucket = now // window
    key = hashlib.sha256(f'{scope}:{subject}:{bucket}'.encode()).hexdigest()
    for _ in range(2):
        changed = AuthenticationLimit.query.filter_by(key=key).update(
            {AuthenticationLimit.count: AuthenticationLimit.count + 1})
        if not changed:
            db.session.add(AuthenticationLimit(key=key, count=1, expires=(bucket + 1) * window))
        try:
            db.session.flush()
            allowed = db.session.get(AuthenticationLimit, key).count <= limit
            db.session.commit()
            return allowed
        except IntegrityError:
            db.session.rollback()
    return False


def _digest(identifier, code):
    return hmac.new(current_app.secret_key.encode(), f'{identifier}:{code}'.encode(), hashlib.sha256).hexdigest()


def issue_challenge(email, deliver):
    if not allow_attempt('otp-email', email, 1, 60):
        return None
    identifier, code = secrets.token_urlsafe(32), f'{secrets.randbelow(1000000):06d}'
    now = int(time.time())
    VerificationChallenge.query.filter_by(email=email, consumed=False).update({'consumed': True})
    challenge = VerificationChallenge(id=identifier, email=email, digest=_digest(identifier, code), expires=now+600)
    db.session.add(challenge)
    db.session.commit()
    try:
        deliver(email, code)
    except Exception:
        VerificationChallenge.query.filter_by(id=identifier).update({'consumed': True})
        db.session.commit()
        current_app.logger.error('Verification email delivery failed; challenge invalidated.')
        return None
    return identifier


def consume_challenge(identifier, code):
    now = int(time.time())
    query = VerificationChallenge.query.filter_by(id=identifier, consumed=False).filter(
        VerificationChallenge.expires > now, VerificationChallenge.attempts < 5)
    # Conditional UPDATE serializes competing attempts, including correct replays.
    if not query.update({VerificationChallenge.attempts: VerificationChallenge.attempts + 1}):
        db.session.rollback()
        return None
    challenge = db.session.get(VerificationChallenge, identifier)
    correct = hmac.compare_digest(challenge.digest, _digest(identifier, code))
    if correct:
        challenge.consumed = True
    email = challenge.email if correct else None
    db.session.commit()
    return email


def cleanup_authentication_state():
    now = int(time.time())
    AuthenticationLimit.query.filter(AuthenticationLimit.expires < now).delete()
    VerificationChallenge.query.filter(VerificationChallenge.expires < now).delete()
    db.session.commit()
