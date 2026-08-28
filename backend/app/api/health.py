from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """
    Базовая проверка живости backend.

    На этом этапе намеренно НЕ проверяем доступность LM Studio —
    это задача этапа 2, когда появится lm_studio_client.
    Здесь только подтверждение, что сам backend поднят и отвечает.
    """
    return {"status": "ok"}