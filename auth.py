"""Master-password login + server-side sessions. Independent of Studio's auth —
no shared session store, no shared cookie, nothing imported from n8n-bpda."""
import hashlib
import hmac
import os
import secrets
import time

SESSION_TTL = 12 * 3600
_sessions: dict[str, float] = {}

_PW_HASH = os.environ.get("SHAD_MASTER_PASSWORD_HASH", "")  # "saltHex$hashHex" (pbkdf2-sha256)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str) -> bool:
    if not _PW_HASH or "$" not in _PW_HASH:
        return False
    salt_hex, hash_hex = _PW_HASH.split("$", 1)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000)
    return hmac.compare_digest(candidate.hex(), hash_hex)


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_TTL
    _gc()
    return token


def check_session(token: str | None) -> bool:
    if not token:
        return False
    exp = _sessions.get(token)
    if exp is None or exp < time.time():
        _sessions.pop(token, None)
        return False
    return True


def destroy_session(token: str | None):
    if token:
        _sessions.pop(token, None)


def _gc():
    now = time.time()
    for t in [t for t, exp in _sessions.items() if exp < now]:
        _sessions.pop(t, None)
