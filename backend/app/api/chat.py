import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.core.exceptions import (
    LMStudioError,
    ModelNotFoundError,
)
from app.schemas.chat import ChatRequest
from app.services.lm_studio_client import LMStudioClient


logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# PROMPTS
# ============================================================

BASE_PATH = Path(__file__).resolve().parents[2]

SYSTEM_PROMPT = (
    BASE_PATH / "prompts" / "system_prompt.txt"
).read_text(encoding="utf-8")

PUBLIC_PROMPT = (
    BASE_PATH / "prompts" / "public_prompt.txt"
).read_text(encoding="utf-8")


# ============================================================
# AUTH
# ============================================================

AUTH_PASSWORD = "ILOVEAIZERE"

authenticated_sessions: set[str] = set()
awaiting_password_sessions: set[str] = set()


# ============================================================
# SSE
# ============================================================

def _sse_event(
    event: str,
    data: dict,
) -> str:

    return (
        f"event: {event}\n"
        f"data: "
        f"{json.dumps(data, ensure_ascii=False)}"
        f"\n\n"
    )


# ============================================================
# CONTENT
# ============================================================

def _get_text_from_content(
    content,
) -> str:

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):

        text_parts: list[str] = []

        for item in content:

            if hasattr(item, "type"):

                if item.type == "text":
                    text_parts.append(
                        item.text
                    )

            elif isinstance(item, dict):

                if item.get("type") == "text":

                    text_parts.append(
                        item.get(
                            "text",
                            "",
                        )
                    )

        return " ".join(
            text_parts
        ).strip()

    return ""


# ============================================================
# MESSAGE SERIALIZATION
# ============================================================

def _serialize_message(
    message,
) -> dict:

    content = message.content

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    if isinstance(content, str):

        return {
            "role": message.role,
            "content": content,
        }

    # --------------------------------------------------------
    # MULTIMODAL
    # --------------------------------------------------------

    serialized_content: list[dict] = []

    for item in content:

        # ====================================================
        # TEXT
        # ====================================================

        if item.type == "text":

            serialized_content.append(
                {
                    "type": "text",
                    "text": item.text,
                }
            )

            continue

        # ====================================================
        # IMAGE
        # ====================================================

        if item.type == "image_url":

            image_url = (
                item.image_url.url
            )

            # Здесь НИЧЕГО не режем.
            #
            # Должно остаться:
            #
            # data:image/jpeg;base64,/9j/4AA...

            if not image_url.startswith(
                "data:image/"
            ):

                raise ValueError(
                    "Image URL must be a "
                    "base64 data URL starting "
                    "with 'data:image/...'"
                )

            if ";base64," not in image_url:

                raise ValueError(
                    "Image URL must contain "
                    "';base64,'."
                )

            serialized_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_url,
                    },
                }
            )

    return {
        "role": message.role,
        "content": serialized_content,
    }


# ============================================================
# GENERATION
# ============================================================

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

        # ====================================================
        # MODEL
        # ====================================================

        available_models = (
            await client.list_models()
        )

        available_ids = {
            model.id
            for model in available_models
        }

        if chat_request.model not in available_ids:

            raise ModelNotFoundError(
                chat_request.model
            )

        session_id = (
            chat_request.session_id
        )

        # ====================================================
        # LAST USER MESSAGE
        # ====================================================

        user_text = ""

        if chat_request.messages:

            user_text = (
                _get_text_from_content(
                    chat_request.messages[
                        -1
                    ].content
                )
            )

        # ====================================================
        # AUTH
        # ====================================================

        if (
            session_id
            not in authenticated_sessions
        ):

            if (
                session_id
                in awaiting_password_sessions
            ):

                if user_text == AUTH_PASSWORD:

                    authenticated_sessions.add(
                        session_id
                    )

                    awaiting_password_sessions.discard(
                        session_id
                    )

                    yield _sse_event(
                        "token",
                        {
                            "content":
                                "Личность подтверждена."
                        },
                    )

                    yield _sse_event(
                        "done",
                        {},
                    )

                    return

                yield _sse_event(
                    "token",
                    {
                        "content":
                            "Пароль неверный."
                    },
                )

                yield _sse_event(
                    "done",
                    {},
                )

                return

            if (
                user_text.casefold()
                == "я ернар"
            ):

                awaiting_password_sessions.add(
                    session_id
                )

                yield _sse_event(
                    "token",
                    {
                        "content":
                            "Подтверди личность паролем."
                    },
                )

                yield _sse_event(
                    "done",
                    {},
                )

                return

        # ====================================================
        # SYSTEM PROMPT
        # ====================================================

        system_prompt = (
            SYSTEM_PROMPT
            if session_id
            in authenticated_sessions
            else PUBLIC_PROMPT
        )

        messages: list[dict] = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

        # ====================================================
        # HISTORY
        # ====================================================

        for message in (
            chat_request.messages
        ):

            messages.append(
                _serialize_message(
                    message
                )
            )

        # ====================================================
        # DEBUG
        # ====================================================

        debug_messages = []

        for message in messages:

            debug_message = {
                "role":
                    message["role"],
                "content":
                    message["content"],
            }

            content = (
                debug_message["content"]
            )

            if isinstance(
                content,
                list,
            ):

                debug_content = []

                for item in content:

                    if (
                        isinstance(
                            item,
                            dict,
                        )
                        and item.get(
                            "type"
                        )
                        == "image_url"
                    ):

                        image_url = (
                            item[
                                "image_url"
                            ][
                                "url"
                            ]
                        )

                        if ";base64," in image_url:

                            prefix, _, base64_data = (
                                image_url.partition(
                                    ";base64,"
                                )
                            )

                            debug_content.append(
                                {
                                    "type":
                                        "image_url",
                                    "image_url":
                                        {
                                            "url":
                                                (
                                                    prefix
                                                    + ";base64,"
                                                    + base64_data[:40]
                                                    + "...[BASE64 HIDDEN]"
                                                )
                                        },
                                }
                            )

                        else:

                            debug_content.append(
                                item
                            )

                    else:

                        debug_content.append(
                            item
                        )

                debug_message[
                    "content"
                ] = debug_content

            debug_messages.append(
                debug_message
            )

        logger.info(
            "FINAL LM STUDIO MESSAGE:\n%s",
            json.dumps(
                debug_messages,
                ensure_ascii=False,
                indent=2,
            ),
        )

        # ====================================================
        # GENERATION
        # ====================================================

        async for token in (
            client.stream_chat_completion(
                model=chat_request.model,
                messages=messages,
                temperature=(
                    chat_request
                    .params
                    .temperature
                ),
                max_tokens=(
                    chat_request
                    .params
                    .max_tokens
                ),
                top_p=(
                    chat_request
                    .params
                    .top_p
                ),
            )
        ):

            if await request.is_disconnected():

                logger.info(
                    "Client disconnected "
                    "mid-stream"
                )

                break

            yield _sse_event(
                "token",
                {
                    "content": token
                },
            )

        yield _sse_event(
            "done",
            {},
        )

    # ========================================================
    # LM STUDIO ERROR
    # ========================================================

    except LMStudioError as exc:

        logger.warning(
            "LM Studio error during "
            "chat stream: %s (%s)",
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

    # ========================================================
    # INVALID MESSAGE
    # ========================================================

    except ValueError as exc:

        logger.exception(
            "Invalid message content"
        )

        yield _sse_event(
            "error",
            {
                "message": str(exc),
                "code": "INVALID_IMAGE",
            },
        )

    # ========================================================
    # CANCELLED
    # ========================================================

    except asyncio.CancelledError:

        logger.info(
            "Chat generation cancelled"
        )

        raise


# ============================================================
# ENDPOINT
# ============================================================

@router.post("/chat")
async def chat(
    chat_request: ChatRequest,
    request: Request,
) -> StreamingResponse:

    return StreamingResponse(
        _generate_sse(
            chat_request,
            request,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )