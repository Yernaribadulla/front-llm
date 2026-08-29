from typing import Literal

from pydantic import BaseModel, Field


class TextContent(BaseModel):
    type: Literal["text"]
    text: str


class ImageURL(BaseModel):
    url: str


class ImageContent(BaseModel):
    type: Literal["image_url"]
    image_url: ImageURL


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str | list[TextContent | ImageContent]


class GenerationParams(BaseModel):
    temperature: float = Field(
        default=0.5,
        ge=0.0,
        le=2.0,
    )

    max_tokens: int = Field(
        default=512,
        ge=1,
        le=32768,
    )

    top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
    )


class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    session_id: str
    system_prompt: str | None = None
    params: GenerationParams = Field(
        default_factory=GenerationParams,
    )