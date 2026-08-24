import socket
from unittest.mock import patch

import pytest

from app.security import assert_public_http_url


def test_rejects_localhost() -> None:
    with pytest.raises(ValueError, match="Локальные"):
        assert_public_http_url("http://localhost/admin")


def test_rejects_private_dns_result() -> None:
    result = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.3", 443))]
    with patch("app.security.socket.getaddrinfo", return_value=result):
        with pytest.raises(ValueError, match="Приватные"):
            assert_public_http_url("https://example.test/")


def test_allows_public_dns_result() -> None:
    result = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    with patch("app.security.socket.getaddrinfo", return_value=result):
        assert_public_http_url("https://example.test/")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.test/file", "/relative"])
def test_rejects_unsupported_urls(url: str) -> None:
    with pytest.raises(ValueError):
        assert_public_http_url(url)
