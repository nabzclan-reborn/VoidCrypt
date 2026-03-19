# VoidCrypt Tests
# Copyright (c) 2026 Nabzclan
# MIT License - https://github.com/nabzclan-reborn/VoidCrypt

"""
VoidCrypt tests.
Run: python3 -m pytest tests/tests.py -v
"""

import os, tempfile
from pathlib import Path

os.environ["VOIDCRYPT_KEY"] = "test-key-for-unit-tests-only"

from voidcrypt import Vault, EntityEngine, EncryptionEngine

class TestEncryption:
    def test_encrypt_decrypt(self):
        enc = EncryptionEngine(os.urandom(32))
        token = enc.encrypt_entity("secret@email.com", "EMAIL")
        assert token == "{email_1}"
        assert enc.decrypt_token(token) == "secret@email.com"

    def test_same_value_same_token(self):
        enc = EncryptionEngine(os.urandom(32))
        t1 = enc.encrypt_entity("test@email.com", "EMAIL")
        t2 = enc.encrypt_entity("test@email.com", "EMAIL")
        assert t1 == t2

    def test_detokenize(self):
        enc = EncryptionEngine(os.urandom(32))
        enc.encrypt_entity("john", "PERSON")
        enc.encrypt_entity("john@test.com", "EMAIL")
        text = "Hello {namep1}, email is {email_1}"
        assert enc.detokenize(text) == "Hello john, email is john@test.com"

    def test_mappings_format(self):
        enc = EncryptionEngine(os.urandom(32))
        enc.encrypt_entity("maria", "PERSON")
        enc.encrypt_entity("maria@work.com", "EMAIL")
        mappings = enc.format_mappings()
        assert '{namep1} => "maria"' in mappings
        assert '{email_1} => "maria@work.com"' in mappings


class TestEntityDetection:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = Vault("test-key", Path(self.tmp) / "test.enc")
        self.engine = EntityEngine(self.vault, level="paranoid", use_encryption=True)

    def test_ssn(self):
        text = "My SSN is 123-45-6789"
        sanitized, redactions = self.engine.scan_and_replace(text)
        assert "123-45-6789" not in sanitized
        assert any(r["type"] == "SSN" for r in redactions)

    def test_email(self):
        text = "Send to john.doe@example.com please"
        sanitized, redactions = self.engine.scan_and_replace(text)
        assert "john.doe@example.com" not in sanitized
        assert any(r["type"] == "EMAIL" for r in redactions)

    def test_phone(self):
        text = "Call me at 555-123-4567"
        sanitized, redactions = self.engine.scan_and_replace(text)
        assert "555-123-4567" not in sanitized
        assert any(r["type"] == "PHONE" for r in redactions)

    def test_credit_card(self):
        text = "Card: 4111 1111 1111 1111"
        sanitized, redactions = self.engine.scan_and_replace(text)
        assert "4111 1111 1111 1111" not in sanitized

    def test_github_token(self):
        text = "gho_faketokenabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        sanitized, redactions = self.engine.scan_and_replace(text)
        assert any(r["type"] == "GITHUB_TOKEN" for r in redactions)

    def test_address(self):
        text = "I live at 123 Main Street"
        sanitized, redactions = self.engine.scan_and_replace(text)
        assert "123 Main Street" not in sanitized
        assert any(r["type"] == "ADDRESS" for r in redactions)

    def test_multiple_entities(self):
        text = "Jane at jane@test.com, SSN 999-88-7777"
        sanitized, redactions = self.engine.scan_and_replace(text)
        assert len(redactions) >= 2

    def test_no_false_positives(self):
        text = "The weather is nice today."
        sanitized, redactions = self.engine.scan_and_replace(text)
        assert sanitized == text
        assert len(redactions) == 0

    def test_restore(self):
        text = "Email me at test@example.com"
        sanitized, _ = self.engine.scan_and_replace(text)
        restored = self.engine.restore(sanitized)
        assert restored == text


class TestSmartLevel:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = Vault("test-key", Path(self.tmp) / "test.enc")
        self.engine = EntityEngine(self.vault, level="smart", use_encryption=True)

    def test_ssn_always_blocked(self):
        text = "SSN: 123-45-6789"
        sanitized, _ = self.engine.scan_and_replace(text)
        assert "123-45-6789" not in sanitized

    def test_email_not_blocked_in_smart(self):
        text = "Contact me at john@google.com"
        sanitized, redactions = self.engine.scan_and_replace(text)
        assert "john@google.com" in sanitized
        assert not any(r["type"] == "EMAIL" for r in redactions)


class TestMinimalLevel:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = Vault("test-key", Path(self.tmp) / "test.enc")
        self.engine = EntityEngine(self.vault, level="minimal", use_encryption=True)

    def test_only_credentials_blocked(self):
        text = "gho_faketokenabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        sanitized, redactions = self.engine.scan_and_replace(text)
        assert any(r["type"] == "GITHUB_TOKEN" for r in redactions)

    def test_phone_not_blocked(self):
        text = "Call 555-123-4567"
        sanitized, redactions = self.engine.scan_and_replace(text)
        assert "555-123-4567" in sanitized


class TestVault:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.vault_path = Path(self.tmp) / "vault.enc"

    def test_persistence(self):
        vault1 = Vault("test-password", self.vault_path)
        token = vault1.get_or_create_token("secret@email.com", "EMAIL")
        vault2 = Vault("test-password", self.vault_path)
        assert vault2.detokenize(token) == "secret@email.com"

    def test_wrong_key_fails(self):
        vault1 = Vault("correct-password", self.vault_path)
        vault1.get_or_create_token("data", "TEST")
        try:
            Vault("wrong-password", self.vault_path)
            assert False
        except Exception:
            pass

    def test_clear(self):
        vault = Vault("test-password", self.vault_path)
        vault.get_or_create_token("data", "TEST")
        assert vault.get_stats()["total_entities"] == 1
        vault.clear_session()
        assert vault.get_stats()["total_entities"] == 0


class TestIntegration:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = Vault("test-key", Path(self.tmp) / "test.enc")
        self.engine = EntityEngine(self.vault, level="paranoid", use_encryption=True)

    def test_full_flow(self):
        original = "Contact maria@example.com. SSN: 123-45-6789"
        sanitized, redactions = self.engine.scan_and_replace(original)
        assert "{email_" in sanitized
        assert "{ssn_" in sanitized
        mappings = self.engine.get_mappings()
        assert len(mappings) == 2
        restored = self.engine.restore(sanitized)
        assert restored == original

    def test_mappings_endpoint_format(self):
        self.engine.scan_and_replace("Contact john@test.com")
        formatted = self.engine.format_mappings()
        for line in formatted:
            assert line.startswith("{")
            assert " => " in line


class TestMultimodal:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = Vault("test-key", Path(self.tmp) / "test.enc")
        self.engine = EntityEngine(self.vault, level="smart", use_encryption=True)

    def test_text_with_ssn(self):
        text = "My SSN is 123-45-6789"
        sanitized, redactions = self.engine.scan_and_replace(text)
        assert sanitized == "My SSN is {ssn_1}"

    def test_image_url_passthrough(self):
        url = "https://example.com/photo.jpg"
        sanitized, redactions = self.engine.scan_and_replace(url)
        assert sanitized == url
        assert len(redactions) == 0

    def test_base64_not_modified(self):
        url = "data:image/png;base64,iVBORw0KG..."
        sanitized, _ = self.engine.scan_and_replace(url)
        assert sanitized == url


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
