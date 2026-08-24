import ipaddress
import socket
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SecretStoreError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().lidoskop_master_key
    if not key:
        raise SecretStoreError("LIDOSKOP_MASTER_KEY не настроен")
    try:
        return Fernet(key.encode())
    except ValueError as exc:
        raise SecretStoreError("LIDOSKOP_MASTER_KEY имеет неверный формат") from exc


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise SecretStoreError("Секрет не удалось расшифровать текущим master key") from exc


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    return f"{value[:3]}••••••{value[-3:]}"


def assert_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Разрешены только абсолютные HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("URL с учётными данными запрещены")
    hostname = parsed.hostname.rstrip(".")
    if hostname.lower() in {"localhost", "localhost.localdomain"}:
        raise ValueError("Локальные адреса запрещены")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, parsed.port or 443)}
    except socket.gaierror as exc:
        raise ValueError("Домен не разрешается через DNS") from exc
    if not addresses:
        raise ValueError("У домена нет адресов")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("Приватные, локальные и служебные IP запрещены")
