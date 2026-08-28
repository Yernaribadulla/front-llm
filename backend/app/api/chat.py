import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.core.exceptions import LMStudioError, ModelNotFoundError
from app.schemas.chat import ChatRequest
from app.services.lm_studio_client import LMStudioClient

logger = logging.getLogger(__name__)

router = APIRouter()


def _sse_event(event: str, data: dict) -> str:
    """
    Формирует одно SSE-сообщение:

        event: <name>
        data: <json>

        <пустая строка>
    """
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


async def _generate_sse(
    chat_request: ChatRequest,
    request: Request,
) -> AsyncGenerator[str, None]:
    settings = get_settings()

    client = LMStudioClient(
        base_url=settings.lm_studio_url,
        timeout=settings.lm_studio_timeout,
    )

    try:
        # Проверяем, что указанная модель действительно доступна
        # в LM Studio.
        available_models = await client.list_models()
        available_ids = {model.id for model in available_models}

        if chat_request.model not in available_ids:
            raise ModelNotFoundError(chat_request.model)

        # Формируем сообщения для OpenAI-compatible API.
        messages: list[dict] = []

        if chat_request.system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": chat_request.system_prompt,
                }
            )

        messages.extend(
            {
                "role": message.role,
                "content": message.content,
            }
            for message in chat_request.messages
        )

        # Получаем токены от LM Studio по мере генерации.
        async for token in client.stream_chat_completion(
            model=chat_request.model,
            messages=messages,
            temperature=chat_request.params.temperature,
            max_tokens=chat_request.params.max_tokens,
            top_p=chat_request.params.top_p,
        ):
            # Если браузер закрыл соединение или нажал Stop —
            # прекращаем генерацию.
            if await request.is_disconnected():
                logger.info(
                    "Client disconnected mid-stream, stopping generation"
                )
                break

            yield _sse_event(
                "token",
                {"content": token},
            )

        # Нормальное завершение генерации.
        yield _sse_event("done", {})

    except LMStudioError as exc:
        logger.warning(
            "LM Studio error during chat stream: %s (%s)",
            exc.message,
            exc.code,
        )

        yield _sse_event(
            "error",
            {
                "message": exc.message,
                "code": exc.code,
            },
        )

    except asyncio.CancelledError:
        logger.info("Chat generation cancelled by client")
        raise


@router.post("/chat")
async def chat(
    chat_request: ChatRequest,
    request: Request,
) -> StreamingResponse:
    return StreamingResponse(
        _generate_sse(chat_request, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )