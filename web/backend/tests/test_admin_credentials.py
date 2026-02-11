"""Tests for web.backend.core.admin_credentials — password utilities."""
import pytest

from web.backend.core.admin_credentials import (
    validate_password_strength,
    generate_password,
    hash_password,
    verify_password,
    MIN_PASSWORD_LENGTH,
)


class TestPasswordValidation:
    """Password strength validation rules."""

    def test_too_short(self):
        ok, err = validate_password_strength("Ab1!")
        assert not ok
        assert "at least" in err

    def test_no_lowercase(self):
        ok, err = validate_password_strength("ABCDEFG1!")
        assert not ok
        assert "lowercase" in err

    def test_no_uppercase(self):
        ok, err = validate_password_strength("abcdefg1!")
        assert not ok
        assert "uppercase" in err

    def test_no_digit(self):
        ok, err = validate_password_strength("Abcdefgh!")
        assert not ok
        assert "digit" in err

    def test_no_special(self):
        ok, err = validate_password_strength("Abcdefg1x")
        assert not ok
        assert "special" in err

    def test_valid_password(self):
        ok, err = validate_password_strength("SecureP@ss1")
        assert ok
        assert err == ""

    def test_minimum_length_boundary(self):
        # Exactly MIN_PASSWORD_LENGTH chars with all required types
        pwd = "Aa1!" + "x" * (MIN_PASSWORD_LENGTH - 4)
        ok, _ = validate_password_strength(pwd)
        assert ok

    def test_one_below_minimum(self):
        pwd = "Aa1!" + "x" * (MIN_PASSWORD_LENGTH - 5)
        ok, _ = validate_password_strength(pwd)
        assert not ok

    def test_empty_password(self):
        ok, _ = validate_password_strength("")
        assert not ok

    def test_various_special_chars(self):
        for char in "!@#$%^&*_+-=":
            ok, _ = validate_password_strength(f"Abcdefg1{char}")
            assert ok, f"Special char '{char}' should be accepted"


class TestPasswordGeneration:
    """Random password generation."""

    def test_default_length(self):
        pwd = generate_password()
        assert len(pwd) == 20

    def test_custom_length(self):
        pwd = generate_password(length=30)
        assert len(pwd) == 30

    def test_contains_required_types(self):
        pwd = generate_password()
        assert any(c.islower() for c in pwd), "Missing lowercase"
        assert any(c.isupper() for c in pwd), "Missing uppercase"
        assert any(c.isdigit() for c in pwd), "Missing digit"
        assert any(not c.isalnum() for c in pwd), "Missing special"

    def test_generated_passes_validation(self):
        for _ in range(10):
            pwd = generate_password()
            ok, err = validate_password_strength(pwd)
            assert ok, f"Generated password '{pwd}' failed validation: {err}"

    def test_uniqueness(self):
        passwords = {generate_password() for _ in range(20)}
        assert len(passwords) == 20, "Generated passwords should be unique"


class TestPasswordHashing:
    """Bcrypt hashing and verification."""

    def test_hash_and_verify(self):
        password = "TestP@ssw0rd!"
        hashed = hash_password(password)
        assert verify_password(password, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("TestP@ssw0rd!")
        assert not verify_password("WrongP@ssw0rd!", hashed)

    def test_hash_is_bcrypt_format(self):
        hashed = hash_password("TestP@ssw0rd!")
        assert hashed.startswith("$2b$")

    def test_different_passwords_different_hashes(self):
        h1 = hash_password("Password1!")
        h2 = hash_password("Password2!")
        assert h1 != h2

    def test_same_password_different_salts(self):
        h1 = hash_password("SameP@ss1")
        h2 = hash_password("SameP@ss1")
        # bcrypt uses random salt each time
        assert h1 != h2

    def test_invalid_hash_returns_false(self):
        assert not verify_password("test", "not-a-valid-hash")

    def test_empty_password_hash(self):
        # Empty password can still be hashed (policy check is separate)
        hashed = hash_password("")
        assert verify_password("", hashed)
