"""Password hashing, JWT session tokens, API-key hashing and secret encryption."""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from quantlab.domain.auth import AuthError, Role

JWT_ALGORITHM = "HS256"
API_KEY_PREFIX = "ql_"
ENCRYPTED_PREFIX = "enc:"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_access_token(username: str, role: Role, secret: str, ttl_minutes: int) -> str:
    payload = {
        "sub": username,
        "role": role.value,
        "exp": datetime.now(UTC) + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret: str) -> tuple[str, Role]:
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
        return str(payload["sub"]), Role(payload["role"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise AuthError("Invalid or expired token") from exc


def generate_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(24)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def fernet_from_secret(secret: str) -> Fernet:
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str, fernet: Fernet) -> str:
    if not value:
        return value
    return ENCRYPTED_PREFIX + fernet.encrypt(value.encode()).decode()


def decrypt_secret(value: str, fernet: Fernet) -> str:
    """Decrypt a stored secret; legacy plaintext values pass through unchanged."""
    if not value.startswith(ENCRYPTED_PREFIX):
        return value
    try:
        return fernet.decrypt(value.removeprefix(ENCRYPTED_PREFIX).encode()).decode()
    except InvalidToken as exc:
        raise AuthError(
            "Stored broker token cannot be decrypted (QL_SECRET_KEY changed?); re-enter it."
        ) from exc
