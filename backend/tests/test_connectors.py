import base64

import httpx
import pytest
import respx

from app.connectors import DaDataConnector, YandexSearchConnector


@pytest.mark.asyncio
@respx.mock
async def test_dadata_maps_company_record() -> None:
    route = respx.post(DaDataConnector.endpoint).mock(
        return_value=httpx.Response(
            200,
            json={
                "suggestions": [
                    {
                        "value": "ООО Ромашка",
                        "unrestricted_value": "ООО Ромашка",
                        "data": {
                            "inn": "1650000000",
                            "ogrn": "1201600000000",
                            "opf": {"full": "Общество с ограниченной ответственностью"},
                            "state": {"status": "ACTIVE"},
                            "address": {
                                "unrestricted_value": "г Казань, ул Тестовая, д 1",
                                "data": {
                                    "federal_district": "Приволжский",
                                    "region_with_type": "Республика Татарстан",
                                    "city": "Казань",
                                },
                            },
                            "management": {"name": "Иванов Иван Иванович", "post": "Директор"},
                        },
                    }
                ]
            },
        )
    )
    records = await DaDataConnector("secret").search("мебель", "Казань")
    assert route.called
    assert records[0].inn == "1650000000"
    assert records[0].city == "Казань"
    assert records[0].manager_name == "Иванов Иван Иванович"


@pytest.mark.asyncio
@respx.mock
async def test_yandex_decodes_xml_urls() -> None:
    xml = b"<yandexsearch><response><results><grouping><group><doc><url>https://example.ru/</url></doc></group></grouping></results></response></yandexsearch>"
    respx.post(YandexSearchConnector.endpoint).mock(
        return_value=httpx.Response(200, json={"rawData": base64.b64encode(xml).decode()})
    )
    urls = await YandexSearchConnector("key", "folder").search("ООО пример")
    assert urls == ["https://example.ru/"]
