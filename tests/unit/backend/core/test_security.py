"""
Unit Tests for Security Module.

Black box tests against the public interface of security.py.
All cryptographic operations (bcrypt, JWT) execute for real.
Only the config boundary is stubbed with real Pydantic schema objects.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from modules.backend.core.config_schema import JwtSchema
from modules.backend.core.exceptions import AuthenticationError
from modules.backend.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    hash_password,
    verify_api_key,
    verify_password,
)

TEST_JWT_SECRET = "test-secret-key-that-is-long-enough-for-testing-purposes"


@pytest.fixture
def jwt_config():
    """Real Pydantic JwtSchema with test values."""
    return JwtSchema(
        algorithm="HS256",
        access_token_expire_minutes=30,
        refresh_token_expire_days=7,
        audience="test-api",
    )


@pytest.fixture
def _stub_config(jwt_config):
    """Stub the config boundary so security functions can resolve settings."""
    settings = SimpleNamespace(jwt_secret=TEST_JWT_SECRET)
    app_config = SimpleNamespace(security=SimpleNamespace(jwt=jwt_config))
    with (
        patch("modules.backend.core.security.get_settings", return_value=settings),
        patch("modules.backend.core.security.get_app_config", return_value=app_config),
    ):
        yield


# =============================================================================
# Password Hashing
# =============================================================================


class TestHashPassword:
    """Tests for password hashing — no mocks, pure black box."""

    def test_returns_hash_different_from_input(self):
        result = hash_password("my-secret-password")
        assert result != "my-secret-password"

    def test_returns_bcrypt_formatted_hash(self):
        result = hash_password("password123")
        assert result.startswith("$2b$")

    def test_same_password_produces_different_hashes(self):
        """Bcrypt salts each hash, so two calls must differ."""
        hash_a = hash_password("identical")
        hash_b = hash_password("identical")
        assert hash_a != hash_b


class TestVerifyPassword:
    """Tests for password verification — no mocks, pure black box."""

    def test_correct_password_verifies(self):
        hashed = hash_password("correct-horse-battery-staple")
        assert verify_password("correct-horse-battery-staple", hashed) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("correct-horse-battery-staple")
        assert verify_password("wrong-password", hashed) is False

    def test_round_trip_with_special_characters(self):
        password = "p@$$w0rd!#%^&*()"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_round_trip_with_unicode(self):
        password = "contraseña-sécurité-пароль"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_empty_password_round_trip(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("not-empty", hashed) is False


# =============================================================================
# JWT Access Tokens
# =============================================================================


@pytest.mark.usefixtures("_stub_config")
class TestCreateAccessToken:
    """Tests for JWT access token creation and decoding — real JWT operations."""

    def test_round_trip_preserves_payload(self):
        token = create_access_token({"sub": "user-42", "role": "admin"})
        payload = decode_token(token)
        assert payload["sub"] == "user-42"
        assert payload["role"] == "admin"

    def test_token_includes_access_type(self):
        token = create_access_token({"sub": "user-1"})
        payload = decode_token(token)
        assert payload["type"] == "access"

    def test_token_includes_expiration(self):
        token = create_access_token({"sub": "user-1"})
        payload = decode_token(token)
        assert "exp" in payload

    def test_custom_expiration_delta(self):
        short = create_access_token({"sub": "u"}, expires_delta=timedelta(minutes=5))
        long = create_access_token({"sub": "u"}, expires_delta=timedelta(hours=24))
        short_exp = decode_token(short)["exp"]
        long_exp = decode_token(long)["exp"]
        assert long_exp > short_exp

    def test_does_not_mutate_input_data(self):
        data = {"sub": "user-1"}
        create_access_token(data)
        assert data == {"sub": "user-1"}


# =============================================================================
# JWT Refresh Tokens
# =============================================================================


@pytest.mark.usefixtures("_stub_config")
class TestCreateRefreshToken:
    """Tests for JWT refresh token creation — real JWT operations."""

    def test_round_trip_preserves_payload(self):
        token = create_refresh_token({"sub": "user-99"})
        payload = decode_token(token)
        assert payload["sub"] == "user-99"

    def test_token_includes_refresh_type(self):
        token = create_refresh_token({"sub": "user-1"})
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_refresh_expires_later_than_access(self):
        access = create_access_token({"sub": "u"})
        refresh = create_refresh_token({"sub": "u"})
        access_exp = decode_token(access)["exp"]
        refresh_exp = decode_token(refresh)["exp"]
        assert refresh_exp > access_exp

    def test_does_not_mutate_input_data(self):
        data = {"sub": "user-1"}
        create_refresh_token(data)
        assert data == {"sub": "user-1"}


# =============================================================================
# Token Decoding — Failure Cases
# =============================================================================


@pytest.mark.usefixtures("_stub_config")
class TestDecodeToken:
    """Tests for token decoding failures — real JWT operations."""

    def test_garbage_token_raises_authentication_error(self):
        with pytest.raises(AuthenticationError):
            decode_token("not-a-jwt-token")

    def test_empty_token_raises_authentication_error(self):
        with pytest.raises(AuthenticationError):
            decode_token("")

    def test_tampered_token_raises_authentication_error(self):
        token = create_access_token({"sub": "user-1"})
        tampered = token[:-4] + "XXXX"
        with pytest.raises(AuthenticationError):
            decode_token(tampered)

    def test_token_signed_with_wrong_secret_raises_authentication_error(self):
        from jose import jwt as jose_jwt

        wrong_token = jose_jwt.encode(
            {"sub": "user-1", "type": "access"},
            "completely-different-secret",
            algorithm="HS256",
        )
        with pytest.raises(AuthenticationError):
            decode_token(wrong_token)

    def test_expired_token_raises_authentication_error(self):
        token = create_access_token(
            {"sub": "user-1"},
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(AuthenticationError):
            decode_token(token)


# =============================================================================
# API Key Generation and Verification
# =============================================================================


class TestGenerateApiKey:
    """Tests for API key generation — no mocks, pure black box."""

    def test_returns_key_and_hash_tuple(self):
        full_key, hashed_key = generate_api_key()
        assert isinstance(full_key, str)
        assert isinstance(hashed_key, str)

    def test_key_has_app_prefix(self):
        full_key, _ = generate_api_key()
        assert full_key.startswith("app_")

    def test_hash_is_bcrypt_formatted(self):
        _, hashed_key = generate_api_key()
        assert hashed_key.startswith("$2b$")

    def test_each_call_produces_unique_key(self):
        key_a, _ = generate_api_key()
        key_b, _ = generate_api_key()
        assert key_a != key_b


class TestVerifyApiKey:
    """Tests for API key verification — no mocks, pure black box."""

    def test_valid_key_verifies(self):
        full_key, hashed_key = generate_api_key()
        assert verify_api_key(full_key, hashed_key) is True

    def test_wrong_key_fails(self):
        _, hashed_key = generate_api_key()
        assert verify_api_key("app_wrong-key", hashed_key) is False

    def test_key_from_different_generation_fails(self):
        key_a, _ = generate_api_key()
        _, hash_b = generate_api_key()
        assert verify_api_key(key_a, hash_b) is False
