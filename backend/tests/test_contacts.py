from unittest.mock import patch

from app.contacts import _check_email_mx


def test_invalid_email_is_rejected_before_dns() -> None:
    assert _check_email_mx("not-an-email") == "invalid_format"


def test_mx_record_marks_domain_valid() -> None:
    with patch("app.contacts.dns.resolver.resolve", return_value=[object()]):
        assert _check_email_mx("sales@example.org") == "mx_valid"
