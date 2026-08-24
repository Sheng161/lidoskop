import json
import time
import uuid
from typing import Any

import httpx
from pydantic import ValidationError

from app.schemas import SearchPlanData, SearchRequest


class GigaChatError(RuntimeError):
    pass


class GigaChatGateway:
    def __init__(self, config: dict[str, Any], authorization_key: str) -> None:
        self.config = config
        self.authorization_key = authorization_key
        self._token: str | None = None
        self._expires_at = 0.0

    async def _access_token(self) -> str:
        if self._token and time.time() < self._expires_at - 30:
            return self._token
        headers = {
            "Authorization": f"Basic {self.authorization_key}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"scope": self.config["scope"]}
        async with httpx.AsyncClient(timeout=self.config["timeout_seconds"]) as client:
            response = await client.post(self.config["oauth_url"], headers=headers, data=data)
        if response.status_code >= 400:
            raise GigaChatError(f"OAuth GigaChat вернул HTTP {response.status_code}")
        payload = response.json()
        self._token = str(payload["access_token"])
        self._expires_at = float(payload.get("expires_at", (time.time() + 1800) * 1000)) / 1000
        return self._token

    async def test_connection(self) -> str:
        token = await self._access_token()
        async with httpx.AsyncClient(timeout=self.config["timeout_seconds"]) as client:
            response = await client.get(
                f"{self.config['base_url'].rstrip('/')}/models",
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            raise GigaChatError(f"Проверка моделей вернула HTTP {response.status_code}")
        return "Подключение установлено"

    async def structured_completion(
        self, system: str, user: str, schema: dict[str, Any], retries: int = 2
    ) -> dict[str, Any]:
        token = await self._access_token()
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": user,
            },
        ]
        for attempt in range(retries + 1):
            async with httpx.AsyncClient(timeout=self.config["timeout_seconds"]) as client:
                response = await client.post(
                    f"{self.config['base_url'].rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "model": self.config["model"],
                        "messages": messages,
                        "functions": [
                            {
                                "name": "submit_structured_result",
                                "description": "Вернуть проверенный структурированный результат",
                                "parameters": schema,
                            }
                        ],
                        "function_call": {"name": "submit_structured_result"},
                        "temperature": self.config["temperature"],
                        "max_tokens": self.config["max_tokens"],
                        "stream": False,
                    },
                )
            if response.status_code >= 400:
                raise GigaChatError(f"GigaChat вернул HTTP {response.status_code}")
            message = response.json()["choices"][0]["message"]
            function_call = message.get("function_call") or {}
            arguments = function_call.get("arguments")
            if isinstance(arguments, dict):
                return dict(arguments)
            content = str(arguments or message.get("content") or "").strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            try:
                return dict(json.loads(content))
            except (json.JSONDecodeError, TypeError, ValueError):
                if attempt == retries:
                    raise GigaChatError("GigaChat не вернул валидный JSON после повторов") from None
                messages.append({"role": "assistant", "content": content[:4000]})
                messages.append({"role": "user", "content": "Исправь JSON строго по схеме."})
        raise AssertionError("unreachable")

    async def build_search_plan(self, request: SearchRequest) -> SearchPlanData:
        system = (
            "Ты планировщик поиска российских организаций. Не создавай факты и сущности. "
            "Выдели только параметры поиска. Используй источники dadata, yandex_search, "
            "official_site. География только Россия."
        )
        payload = await self.structured_completion(
            system,
            request.model_dump_json(),
            SearchPlanData.model_json_schema(),
        )
        try:
            plan = SearchPlanData.model_validate(payload)
        except ValidationError as exc:
            raise GigaChatError("План GigaChat не прошёл проверку схемы") from exc
        if request.city:
            plan.city = request.city
        if request.region:
            plan.region = request.region
        if request.target_roles:
            plan.target_roles = request.target_roles
        return plan
