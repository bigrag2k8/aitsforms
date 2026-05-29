"""Password hashing and session tokens (stdlib only — no external crypto deps).

Passwords use scrypt (memory-hard) with a per-password random salt. Stored form:
    scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import secrets

_N = 16384  # CPU/memory cost
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s.encode("ascii"))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(_unb64(hash_b64)),
        )
        return hmac.compare_digest(dk, _unb64(hash_b64))
    except Exception:
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)
