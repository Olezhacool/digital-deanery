"""Пароли и подписанные cookie-сессии. Только стандартная библиотека."""
import hashlib
import hmac
import secrets
import time

PBKDF2_ITERATIONS = 150_000
SESSION_TTL = 7 * 24 * 3600


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return salt, digest.hex()


def verify_password(password: str, salt: str, expected: str) -> bool:
    _, digest = hash_password(password, salt)
    return hmac.compare_digest(digest, expected)


def make_session(user_id: int, secret: str, ttl: int = SESSION_TTL) -> str:
    expires = int(time.time()) + ttl
    payload = f"{user_id}.{expires}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def read_session(token: str, secret: str) -> int | None:
    try:
        user_id, expires, signature = token.split(".")
    except (AttributeError, ValueError):
        return None
    payload = f"{user_id}.{expires}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    if int(expires) < time.time():
        return None
    return int(user_id)
