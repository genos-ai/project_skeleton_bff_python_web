"""
Security Utilities.

Authentication, authorization, and security helpers.
"""

from datetime import timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from modules.backend.core.config import get_app_config, get_settings
from modules.backend.core.exceptions import AuthenticationError
from modules.backend.core.logging import get_logger
from modules.backend.core.utils import utc_now

logger = get_logger(__name__)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Payload data to encode
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token
    """
    settings = get_settings()
    jwt_config = get_app_config().security.jwt
    to_encode = data.copy()

    if expires_delta:
        expire = utc_now() + expires_delta
    else:
        expire = utc_now() + timedelta(minutes=jwt_config.access_token_expire_minutes)

    to_encode.update({"exp": expire, "type": "access", "aud": jwt_config.audience})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm=jwt_config.algorithm)
    return encoded_jwt


def create_refresh_token(data: dict[str, Any]) -> str:
    """
    Create a JWT refresh token.

    Args:
        data: Payload data to encode

    Returns:
        Encoded JWT refresh token
    """
    settings = get_settings()
    jwt_config = get_app_config().security.jwt
    to_encode = data.copy()
    expire = utc_now() + timedelta(days=jwt_config.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh", "aud": jwt_config.audience})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm=jwt_config.algorithm)
    return encoded_jwt


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded token payload

    Raises:
        AuthenticationError: If token is invalid or expired
    """
    settings = get_settings()
    jwt_config = get_app_config().security.jwt
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[jwt_config.algorithm],
            audience=jwt_config.audience,
        )
        return payload
    except JWTError as e:
        logger.warning("Token decode failed", extra={"error": str(e)})
        raise AuthenticationError("Invalid or expired token")


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key.

    Returns:
        Tuple of (full_key, hashed_key)
        - full_key: Show to user once
        - hashed_key: Store in database
    """
    import secrets

    # Generate 32-byte random key
    random_part = secrets.token_urlsafe(32)
    full_key = f"app_{random_part}"

    # Hash for storage
    hashed_key = hash_password(full_key)

    return full_key, hashed_key


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Verify an API key against its hash."""
    return verify_password(plain_key, hashed_key)
