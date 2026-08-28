import json
from collections.abc import AsyncGenerator

import httpx

from app.core.exceptions import (
    LMStudioHTTPError,
    LMStudioTimeoutError,
    LMStudioUnreachableError,
    MalformedResponseError,
)
from app.schemas.models import ModelInfo


class LMStudioClient:
    """
    Тонкая обёртка над LM Studio OpenAI-compatible API.

    Инстанцируется один раз с базовым URL и таймаутом из конфига (Settings),
    ничего не хардкодит и не читает env самостоятельно — конфигурация
    приходит извне, что упрощает тестирование (можно передать mock URL).
    """

    def __init__(self, base_url: str, timeout: int):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def list_models(self) -> list[ModelInfo]:
        """
        Запрашивает GET {base_url}/models у LM Studio.

        Поднимает конкретные исключения из core.exceptions вместо того,
        чтобы пробрасывать httpx-исключения наружу — вызывающий код
        не должен знать про httpx вообще.
        """
        url = f"{self._base_url}/models"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
        except httpx.ConnectError as exc:
            raise LMStudioUnreachableError(
                f"Could not connect to LM Studio at {self._base_url}. "
                "Make sure LM Studio is running and the Local Server is started."
            ) from exc
        except httpx.TimeoutException as exc:
            raise LMStudioTimeoutError(
                f"LM Studio did not respond within {self._timeout}s"
            ) from exc
        except httpx.RequestError as exc:
            raise LMStudioUnreachableError(
                f"Network error while contacting LM Studio: {exc}"
            ) from exc

        if response.status_code != 200:
            raise LMStudioHTTPError(
                status_code=response.status_code,
                message=f"LM Studio responded with status {response.status_code}",
            )

        try:
            payload = response.json()
            raw_models = payload["data"]
            return [ModelInfo(id=item["id"]) for item in raw_models]
        except (KeyError, TypeError, ValueError) as exc:
            raise MalformedResponseError(
                f"Could not parse LM Studio /models response: {exc}"
            ) from exc

    async def stream_chat_completion(
        self,
        *,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        top_p: float,
    ) -> AsyncGenerator[str, None]:
        """
        Стримит chat completion от LM Studio POST {base_url}/chat/completions.

        Yield'ит только текстовое содержимое токена (str), очищенное
        от протокола OpenAI streaming-формата. Вызывающий код (api/chat.py)
        не должен парсить SSE-формат LM Studio самостоятельно.

        Особенности OpenAI-compatible streaming, которые здесь учтены:
        - каждая строка данных имеет вид "data: {...}";
        - поток завершается строкой "data: [DONE]" (не JSON!);
        - контент лежит в choices[0].delta.content и может отсутствовать
          (например, в самом последнем содержательном чанке, где delta пуст,
          а причина остановки — в choices[0].finish_reason).
        """
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        raise LMStudioHTTPError(
                            status_code=response.status_code,
                            message=(
                                f"LM Studio responded with status {response.status_code}: "
                                f"{body.decode(errors='ignore')[:200]}"
                            ),
                        )

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            # Пустые строки — разделители SSE-событий,
                            # строки без "data: " — не наш формат, пропускаем.
                            continue

                        data = line[len("data: "):].strip()

                        if data == "[DONE]":
                            return

                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError as exc:
                            raise MalformedResponseError(
                                f"Could not parse LM Studio stream chunk: {exc}"
                            ) from exc

                        try:
                            choices = chunk["choices"]
                            if not choices:
                                continue
                            content = choices[0].get("delta", {}).get("content")
                        except (KeyError, IndexError, TypeError) as exc:
                            raise MalformedResponseError(
                                f"Unexpected chunk structure from LM Studio: {exc}"
                            ) from exc

                        if content:
                            yield content

        except httpx.ConnectError as exc:
            raise LMStudioUnreachableError(
                f"Could not connect to LM Studio at {self._base_url}. "
                "Make sure LM Studio is running and the Local Server is started."
            ) from exc
        except httpx.TimeoutException as exc:
            raise LMStudioTimeoutError(
                f"LM Studio did not respond within {self._timeout}s"
            ) from exc
        except httpx.RequestError as exc:
            # Покрывает и обрывы соединения посреди стрима
            # (например httpx.RemoteProtocolError), не только на старте.
            raise LMStudioUnreachableError(
                f"Network error while streaming from LM Studio: {exc}"
            ) from exc