import base64
import json
from dataclasses import dataclass
from typing import Any

import httpx
from defusedxml import ElementTree


class ConnectorError(RuntimeError):
    pass


@dataclass
class CompanyRecord:
    name: str
    inn: str | None
    ogrn: str | None
    legal_form: str | None
    status: str | None
    address: str | None
    federal_district: str | None
    region: str | None
    city: str | None
    manager_name: str | None
    manager_post: str | None
    raw: dict[str, Any]


class DaDataConnector:
    endpoint = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"

    def __init__(self, token: str, timeout: float = 15) -> None:
        self.token = token
        self.timeout = timeout

    async def search(self, query: str, city: str | None, count: int = 20) -> list[CompanyRecord]:
        payload: dict[str, Any] = {"query": query, "count": min(count, 20)}
        if city:
            payload["locations"] = [{"city": city}]
            payload["restrict_value"] = True
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.endpoint,
                headers={"Authorization": f"Token {self.token}"},
                json=payload,
            )
        if response.status_code >= 400:
            raise ConnectorError(f"DaData вернул HTTP {response.status_code}")
        records: list[CompanyRecord] = []
        for item in response.json().get("suggestions", []):
            data = item.get("data", {})
            address_data = (data.get("address") or {}).get("data") or {}
            management = data.get("management") or {}
            records.append(
                CompanyRecord(
                    name=item.get("unrestricted_value") or item.get("value") or "",
                    inn=data.get("inn"),
                    ogrn=data.get("ogrn"),
                    legal_form=(data.get("opf") or {}).get("full"),
                    status=(data.get("state") or {}).get("status"),
                    address=(data.get("address") or {}).get("unrestricted_value"),
                    federal_district=address_data.get("federal_district"),
                    region=address_data.get("region_with_type"),
                    city=address_data.get("city") or address_data.get("settlement"),
                    manager_name=management.get("name"),
                    manager_post=management.get("post"),
                    raw=data,
                )
            )
        return records

    async def test_connection(self) -> str:
        await self.search("Сбербанк", "Москва", 1)
        return "DaData подключён"


class YandexSearchConnector:
    endpoint = "https://searchapi.api.cloud.yandex.net/v2/web/search"

    def __init__(self, api_key: str, folder_id: str, timeout: float = 20) -> None:
        self.api_key = api_key
        self.folder_id = folder_id
        self.timeout = timeout

    async def search(self, query: str, limit: int = 10) -> list[str]:
        body = {
            "query": {
                "searchType": "SEARCH_TYPE_RU",
                "queryText": query,
                "familyMode": "FAMILY_MODE_MODERATE",
                "page": "0",
            },
            "folderId": self.folder_id,
            "responseFormat": "FORMAT_XML",
            "userAgent": "Lidoskop/0.1",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.endpoint, headers={"Authorization": f"Api-Key {self.api_key}"}, json=body
            )
        if response.status_code >= 400:
            raise ConnectorError(f"Yandex Search API вернул HTTP {response.status_code}")
        raw = response.json().get("rawData", "")
        try:
            root = ElementTree.fromstring(base64.b64decode(raw))
        except (ValueError, ElementTree.ParseError) as exc:
            raise ConnectorError("Yandex Search API вернул некорректный XML") from exc
        urls = [node.text for node in root.findall(".//url") if node.text]
        return urls[:limit]

    async def test_connection(self) -> str:
        await self.search("официальный сайт ФНС России", 1)
        return "Yandex Search API подключён"


def safe_evidence_excerpt(record: CompanyRecord) -> str:
    allowed = {
        "name": record.name,
        "inn": record.inn,
        "ogrn": record.ogrn,
        "status": record.status,
        "address": record.address,
        "management": {"name": record.manager_name, "post": record.manager_post},
    }
    return json.dumps(allowed, ensure_ascii=False)[:4000]
