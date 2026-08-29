import json
from collections.abc import AsyncGenerator
from typing import Any

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
    Клиент для OpenAI-compatible API LM Studio.
    """

    def __init__(self, base_url: str, timeout: int):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    # =========================================================
    # MODELS
    # =========================================================

    async def list_models(self) -> list[ModelInfo]:
        url = f"{self._base_url}/models"

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout
            ) as client:
                response = await client.get(url)

        except httpx.ConnectError as exc:
            raise LMStudioUnreachableError(
                f"Could not connect to LM Studio at "
                f"{self._base_url}. "
                "Make sure LM Studio is running "
                "and the Local Server is started."
            ) from exc

        except httpx.TimeoutException as exc:
            raise LMStudioTimeoutError(
                f"LM Studio did not respond within "
                f"{self._timeout}s"
            ) from exc

        except httpx.RequestError as exc:
            raise LMStudioUnreachableError(
                f"Network error while contacting "
                f"LM Studio: {exc}"
            ) from exc

        if response.status_code != 200:
            raise LMStudioHTTPError(
                status_code=response.status_code,
                message=(
                    f"LM Studio responded with status "
                    f"{response.status_code}"
                ),
            )

        try:
            payload = response.json()
            raw_models = payload["data"]

            return [
                ModelInfo(id=item["id"])
                for item in raw_models
            ]

        except (KeyError, TypeError, ValueError) as exc:
            raise MalformedResponseError(
                f"Could not parse LM Studio "
                f"/models response: {exc}"
            ) from exc

    # =========================================================
    # IMAGE VALIDATION
    # =========================================================

    @staticmethod
    def _validate_image_url(url: str) -> str:
        """
        Проверяет изображение.

        LM Studio получает изображение как полный
        Data URL:

            data:image/jpeg;base64,/9j/4AAQ...

        ВАЖНО:
        Data URL НЕ обрезается и НЕ преобразуется
        в чистую base64-строку.
        """

        url = url.strip()

        if not url:
            raise ValueError(
                "Image URL is empty."
            )

        if not url.startswith("data:image/"):
            raise ValueError(
                "Image URL must be a base64 data URL "
                "starting with 'data:image/...'"
            )

        if ";base64," not in url:
            raise ValueError(
                "Image URL must contain ';base64,'."
            )

        prefix, base64_data = url.split(
            ";base64,",
            1,
        )

        if not prefix.startswith("data:image/"):
            raise ValueError(
                "Invalid image MIME type."
            )

        if not base64_data.strip():
            raise ValueError(
                "Image base64 data is empty."
            )

        return url

    # =========================================================
    # MESSAGE PREPARATION
    # =========================================================

    def _prepare_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Подготавливает сообщения для LM Studio.

        Текст:

            {
                "type": "text",
                "text": "Привет"
            }

        Изображение:

            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64,..."
                }
            }
        """

        prepared_messages: list[dict[str, Any]] = []

        for message in messages:
            role = message.get("role")
            content = message.get("content")

            # -------------------------------------------------
            # STRING CONTENT
            # -------------------------------------------------

            if isinstance(content, str):
                prepared_messages.append(
                    {
                        "role": role,
                        "content": content,
                    }
                )

                continue

            # -------------------------------------------------
            # MULTIMODAL CONTENT
            # -------------------------------------------------

            if isinstance(content, list):
                prepared_content: list[dict[str, Any]] = []

                for item in content:

                    if not isinstance(item, dict):
                        continue

                    item_type = item.get("type")

                    # -----------------------------------------
                    # TEXT
                    # -----------------------------------------

                    if item_type == "text":

                        text = item.get("text", "")

                        if not isinstance(text, str):
                            text = str(text)

                        prepared_content.append(
                            {
                                "type": "text",
                                "text": text,
                            }
                        )

                        continue

                    # -----------------------------------------
                    # IMAGE
                    # -----------------------------------------

                    if item_type == "image_url":

                        image_data = item.get(
                            "image_url"
                        )

                        if not isinstance(
                            image_data,
                            dict,
                        ):
                            raise ValueError(
                                "image_url must be an object."
                            )

                        raw_url = image_data.get("url")

                        # ВАЖНО:
                        # Отдельно проверяем тип.
                        # Это убирает ошибку Pylance:
                        #
                        # Unknown | None -> str

                        if not isinstance(
                            raw_url,
                            str,
                        ):
                            raise ValueError(
                                "image_url.url must be a string."
                            )

                        image_url = (
                            self._validate_image_url(
                                raw_url
                            )
                        )

                        prepared_content.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url,
                                },
                            }
                        )

                        continue

                prepared_messages.append(
                    {
                        "role": role,
                        "content": prepared_content,
                    }
                )

                continue

            raise ValueError(
                "Unsupported message content type: "
                f"{type(content).__name__}"
            )

        return prepared_messages

    # =========================================================
    # DEBUG
    # =========================================================

    @staticmethod
    def _create_debug_payload(
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Создаёт копию payload для логирования.

        Реальная base64 НЕ изменяется.

        В консоль выводится только начало Data URL.
        """

        debug_payload = json.loads(
            json.dumps(payload)
        )

        messages = debug_payload.get(
            "messages",
            [],
        )

        if not isinstance(messages, list):
            return debug_payload

        for message in messages:

            if not isinstance(message, dict):
                continue

            content = message.get("content")

            if not isinstance(content, list):
                continue

            for item in content:

                if not isinstance(item, dict):
                    continue

                if item.get("type") != "image_url":
                    continue

                image_data = item.get(
                    "image_url"
                )

                if not isinstance(
                    image_data,
                    dict,
                ):
                    continue

                image_url = image_data.get(
                    "url"
                )

                if not isinstance(
                    image_url,
                    str,
                ):
                    continue

                if ";base64," not in image_url:
                    continue

                prefix, _, base64_data = (
                    image_url.partition(
                        ";base64,"
                    )
                )

                image_data["url"] = (
                    prefix
                    + ";base64,"
                    + base64_data[:40]
                    + "...[BASE64 HIDDEN]"
                )

        return debug_payload

    # =========================================================
    # CHAT COMPLETION
    # =========================================================

    async def stream_chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        top_p: float,
    ) -> AsyncGenerator[str, None]:

        url = f"{self._base_url}/chat/completions"

        # -----------------------------------------------------
        # PREPARE
        # -----------------------------------------------------

        prepared_messages = self._prepare_messages(
            messages
        )

        payload: dict[str, Any] = {
            "model": model,
            "messages": prepared_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": True,
        }

        # -----------------------------------------------------
        # DEBUG
        # -----------------------------------------------------

        debug_payload = self._create_debug_payload(
            payload
        )

        print()
        print("=" * 70)
        print("REQUEST TO LM STUDIO")
        print("=" * 70)

        print(
            json.dumps(
                debug_payload,
                ensure_ascii=False,
                indent=2,
            )
        )

        print("=" * 70)
        print()

        # -----------------------------------------------------
        # REQUEST
        # -----------------------------------------------------

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout
            ) as client:

                async with client.stream(
                    "POST",
                    url,
                    json=payload,
                ) as response:

                    if response.status_code != 200:

                        body = await response.aread()

                        error_text = body.decode(
                            errors="ignore"
                        )

                        print()
                        print("=" * 70)
                        print("LM STUDIO ERROR")
                        print("=" * 70)
                        print(error_text)
                        print("=" * 70)
                        print()

                        raise LMStudioHTTPError(
                            status_code=response.status_code,
                            message=(
                                "LM Studio responded with "
                                f"status {response.status_code}: "
                                f"{error_text[:1000]}"
                            ),
                        )

                    # =========================================
                    # SSE STREAM
                    # =========================================

                    async for line in response.aiter_lines():

                        if not line:
                            continue

                        if not line.startswith(
                            "data: "
                        ):
                            continue

                        data = line[
                            len("data: "):
                        ].strip()

                        if data == "[DONE]":
                            return

                        try:
                            chunk = json.loads(data)

                        except json.JSONDecodeError as exc:
                            raise MalformedResponseError(
                                "Could not parse LM Studio "
                                f"stream chunk: {exc}"
                            ) from exc

                        try:
                            choices = chunk["choices"]

                            if not choices:
                                continue

                            delta = choices[0].get(
                                "delta",
                                {},
                            )

                            content = delta.get(
                                "content"
                            )

                        except (
                            KeyError,
                            IndexError,
                            TypeError,
                        ) as exc:

                            raise MalformedResponseError(
                                "Unexpected chunk structure "
                                f"from LM Studio: {exc}"
                            ) from exc

                        if isinstance(
                            content,
                            str,
                        ) and content:

                            yield content

        # -----------------------------------------------------
        # CONNECTION ERROR
        # -----------------------------------------------------

        except httpx.ConnectError as exc:

            raise LMStudioUnreachableError(
                f"Could not connect to LM Studio at "
                f"{self._base_url}. "
                "Make sure LM Studio is running "
                "and the Local Server is started."
            ) from exc

        # -----------------------------------------------------
        # TIMEOUT
        # -----------------------------------------------------

        except httpx.TimeoutException as exc:

            raise LMStudioTimeoutError(
                f"LM Studio did not respond within "
                f"{self._timeout}s"
            ) from exc

        # -----------------------------------------------------
        # OTHER HTTPX ERROR
        # -----------------------------------------------------

        except httpx.RequestError as exc:

            raise LMStudioUnreachableError(
                f"Network error while streaming "
                f"from LM Studio: {exc}"
            ) from exc