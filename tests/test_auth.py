"""Passcode hashing + verification."""

from __future__ import annotations

import pytest

from growth import auth


class TestValidatePasscode:
    def test_too_short_raises(self):
        with pytest.raises(auth.InvalidPasscode):
            auth.validate_passcode("abc")

    def test_min_length_ok(self):
        # MIN_PASSCODE_LENGTH chars exactly should pass.
        auth.validate_passcode("a" * auth.MIN_PASSCODE_LENGTH)

    def test_non_string_raises(self):
        with pytest.raises(auth.InvalidPasscode):
            auth.validate_passcode(123456)  # type: ignore[arg-type]


class TestHashAndVerify:
    def test_verify_accepts_correct_passcode(self):
        h = auth.hash_passcode("hunter2!")
        assert auth.verify_passcode("hunter2!", h) is True

    def test_verify_rejects_wrong_passcode(self):
        h = auth.hash_passcode("hunter2!")
        assert auth.verify_passcode("hunter3!", h) is False

    def test_different_salts_produce_different_hashes(self):
        a = auth.hash_passcode("samepass")
        b = auth.hash_passcode("samepass")
        assert a != b
        # Both should still verify against the same passcode.
        assert auth.verify_passcode("samepass", a)
        assert auth.verify_passcode("samepass", b)

    def test_hash_format(self):
        h = auth.hash_passcode("abc123")
        parts = h.split("$")
        assert len(parts) == 4
        assert parts[0] == "pbkdf2_sha256"
        assert int(parts[1]) > 0

    def test_verify_rejects_garbage_hash(self):
        assert auth.verify_passcode("anything", "not-a-real-hash") is False
        assert auth.verify_passcode("anything", "pbkdf2_sha256$not$an$int") is False
        assert auth.verify_passcode("anything", "") is False

    def test_verify_rejects_wrong_algorithm(self):
        # A well-formed string but with an unknown algorithm token.
        bogus = "md5$1$Zm9v$YmFy"
        assert auth.verify_passcode("foo", bogus) is False

    def test_unicode_passcode_round_trips(self):
        pw = "pässwörd_ñ"
        h = auth.hash_passcode(pw)
        assert auth.verify_passcode(pw, h)
        assert not auth.verify_passcode("password_n", h)
