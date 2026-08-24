import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSetting, SourceConnector
from app.security import decrypt_secret, encrypt_secret


async def get_gigachat_config(session: AsyncSession) -> tuple[dict[str, Any], str] | None:
    row = await session.get(AppSetting, "gigachat")
    if not row or not row.encrypted_value or not row.public_value:
        return None
    return dict(row.public_value), decrypt_secret(row.encrypted_value)


async def save_gigachat_config(
    session: AsyncSession, public_config: dict[str, Any], authorization_key: str | None
) -> AppSetting:
    row = await session.get(AppSetting, "gigachat")
    if row is None:
        if not authorization_key:
            raise ValueError("Authorization Key обязателен при первой настройке")
        row = AppSetting(key="gigachat")
        session.add(row)
    row.public_value = public_config
    if authorization_key:
        row.encrypted_value = encrypt_secret(authorization_key)
    await session.flush()
    return row


async def get_connector_config(
    session: AsyncSession, kind: str
) -> tuple[SourceConnector, dict[str, str]] | None:
    row = await session.scalar(select(SourceConnector).where(SourceConnector.kind == kind))
    if not row:
        return None
    config = json.loads(decrypt_secret(row.encrypted_config)) if row.encrypted_config else {}
    return row, config


async def save_connector_config(
    session: AsyncSession,
    kind: str,
    display_name: str,
    is_enabled: bool,
    rate_limit_per_minute: int,
    config: dict[str, str],
) -> SourceConnector:
    row = await session.scalar(select(SourceConnector).where(SourceConnector.kind == kind))
    if row is None:
        row = SourceConnector(kind=kind, display_name=display_name)
        session.add(row)
    row.display_name = display_name
    row.is_enabled = is_enabled
    row.rate_limit_per_minute = rate_limit_per_minute
    if config:
        row.encrypted_config = encrypt_secret(json.dumps(config))
    row.status = "connected" if is_enabled and row.encrypted_config else "not_connected"
    await session.flush()
    return row
