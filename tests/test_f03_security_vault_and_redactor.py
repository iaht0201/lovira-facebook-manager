import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.lovira.security.vault import SecretVault
from src.lovira.security.redactor import LogRedactor, RedactingLogFilter


def test_secret_vault_fallback_encryption():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_dir = Path(tmpdir)
        vault = SecretVault(fallback_vault_dir=vault_dir)

        # Force keyring failure to test AC-33 (safe AES-256-GCM fallback without plaintext)
        with patch("keyring.set_password", side_effect=RuntimeError("Keyring unavailable")):
            with patch("keyring.get_password", return_value=None):
                provider = vault.set_secret("fb_page_token_123", "EAABsecret_token_123456789")
                assert provider == "local_vault"

                # Verify file on disk is encrypted, does NOT contain raw token string
                enc_file = vault_dir / "fb_page_token_123.enc"
                assert enc_file.exists()
                raw_disk_content = enc_file.read_text(encoding="utf-8")
                assert "EAABsecret_token_123456789" not in raw_disk_content

                # Retrieve and decrypt
                retrieved = vault.get_secret("fb_page_token_123")
                assert retrieved == "EAABsecret_token_123456789"

                # Delete
                assert vault.delete_secret("fb_page_token_123") is True
                assert vault.get_secret("fb_page_token_123") is None


def test_log_redactor_text():
    raw_log = (
        "Calling Graph API with token EAABtesttoken1234567890abcdef and header Bearer eyJhbGciOi.eyJzdWIi.signature "
        "using license LOVI-1234-ABCD-5678 and cookie xs=abc123xyz"
    )
    redacted = LogRedactor.redact_text(raw_log)

    assert "EAABtesttoken1234567890abcdef" not in redacted
    assert "EAA[REDACTED_FB_TOKEN]" in redacted
    assert "Bearer [REDACTED]" in redacted
    assert "[REDACTED_KEY]" in redacted
    assert "[REDACTED_COOKIE]" in redacted


def test_log_redactor_dict():
    payload = {
        "page_id": "1001",
        "access_token": "EAABverysecrettoken12345",
        "nested": {
            "password": "mypassword123",
            "normal_field": "hello world",
        },
        "license_key": "LOVI-9999-8888-7777",
    }
    cleaned = LogRedactor.redact_dict(payload)

    assert cleaned["page_id"] == "1001"
    assert cleaned["access_token"] == "[REDACTED]"
    assert cleaned["nested"]["password"] == "[REDACTED]"
    assert cleaned["nested"]["normal_field"] == "hello world"
    assert cleaned["license_key"] == "[REDACTED]"


def test_redacting_log_filter(caplog):
    logger = logging.getLogger("test_redaction_logger")
    logger.setLevel(logging.INFO)
    log_filter = RedactingLogFilter()
    logger.addFilter(log_filter)

    with caplog.at_level(logging.INFO):
        logger.info("Connecting with Facebook token EAABsecrettoken123456789")

    captured = caplog.text
    assert "EAABsecrettoken123456789" not in captured
    assert "EAA[REDACTED_FB_TOKEN]" in captured
