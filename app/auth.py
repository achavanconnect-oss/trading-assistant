"""Password hashing (scrypt, stdlib) and JWT access tokens (PyJWT, HS256)."""
import hashlib
import hmac
import os
import time

import jwt

TOKEN_TTL_S = int(os.getenv("JWT_TTL_S") or 3600)
MIN_PASSWORD_LEN = 8
MIN_SECRET_LEN = 32


class AuthError(Exception):
    pass


def auth_required() -> bool:
    """Off by default so the local demo works with no login. Set AUTH_REQUIRED=1 for any shared deployment."""
    return os.getenv("AUTH_REQUIRED") == "1"


def _secret() -> str:
    s = os.getenv("JWT_SECRET")
    if not s:
        raise AuthError("JWT_SECRET is not set")
    if len(s) < MIN_SECRET_LEN:
        raise AuthError(f"JWT_SECRET must be at least {MIN_SECRET_LEN} characters")
    return s


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(h.hex(), hash_hex)
    except ValueError:
        return False


# A real hash to compare against when the email is unknown, so "no such user" and "wrong password" take similar time.
_DUMMY_HASH = hash_password("not-a-real-password")


def create_token(user_id: int, email: str, ttl_s: int | None = None) -> str:
    now = int(time.time())
    return jwt.encode({"sub": str(user_id), "email": email, "iat": now, "exp": now + (TOKEN_TTL_S if ttl_s is None else ttl_s)},
                      _secret(), algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError as e:
        raise AuthError(str(e)) from e
