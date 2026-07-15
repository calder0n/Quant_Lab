"""Tests for hashing, tokens and secret encryption."""

import pytest

from quantlab.domain.auth import AuthError, Role
from quantlab.infrastructure.security import (
    create_access_token,
    decode_access_token,
    decrypt_secret,
    encrypt_secret,
    fernet_from_secret,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip() -> None:
    hashed = hash_password("s3cret-password")
    assert hashed != "s3cret-password"
    assert verify_password("s3cret-password", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("s3cret-password", "not-a-hash")


def test_jwt_round_trip_and_tampering() -> None:
    token = create_access_token("alice", Role.ADMIN, secret="k1", ttl_minutes=5)
    username, role = decode_access_token(token, "k1")
    assert (username, role) == ("alice", Role.ADMIN)
    with pytest.raises(AuthError):
        decode_access_token(token, "other-secret")
    with pytest.raises(AuthError):
        decode_access_token(token + "x", "k1")


def test_expired_token_is_rejected() -> None:
    token = create_access_token("alice", Role.VIEWER, secret="k1", ttl_minutes=-1)
    with pytest.raises(AuthError):
        decode_access_token(token, "k1")


def test_api_keys_are_prefixed_and_hash_deterministically() -> None:
    key = generate_api_key()
    assert key.startswith("ql_")
    assert hash_api_key(key) == hash_api_key(key)
    assert hash_api_key(key) != hash_api_key(generate_api_key())


def test_secret_encryption_round_trip_and_legacy_passthrough() -> None:
    fernet = fernet_from_secret("my-secret-key")
    encrypted = encrypt_secret("oanda-token-123", fernet)
    assert encrypted.startswith("enc:")
    assert "oanda-token-123" not in encrypted
    assert decrypt_secret(encrypted, fernet) == "oanda-token-123"
    # legacy plaintext rows pass through untouched
    assert decrypt_secret("plaintext-token", fernet) == "plaintext-token"
    assert encrypt_secret("", fernet) == ""


def test_decrypt_with_wrong_key_raises() -> None:
    encrypted = encrypt_secret("token", fernet_from_secret("key-a"))
    with pytest.raises(AuthError, match="re-enter"):
        decrypt_secret(encrypted, fernet_from_secret("key-b"))
