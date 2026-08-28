from fastapi import APIRouter

from app.config import get_settings
from app.core.exceptions import LMStudioError
from app.schemas.models import ModelsResponse
from app.services.lm_studio_client import LMStudioClient

router = APIRouter()


@router.get("/models", response_model=ModelsResponse)
async def get_models() -> ModelsResponse:
    """
    Возвращает список моделей, загруженных в LM Studio.

    Намеренно НЕ поднимает 5xx, если LM Studio недоступен — это ожидаемое
    состояние в локальной разработке (пользователь ещё не запустил LM Studio),
    а не ошибка backend. Вместо этого отдаём 200 с lm_studio_available=False,
    и фронт показывает статус-индикатор вместо страницы с ошибкой.
    """
    settings = get_settings()
    client = LMStudioClient(
        base_url=settings.lm_studio_url,
        timeout=settings.lm_studio_timeout,
    )

    try:
        models = await client.list_models()
    except LMStudioError:
        return ModelsResponse(models=[], lm_studio_available=False)

    return ModelsResponse(models=models, lm_studio_available=True)