from pydantic import BaseModel


class ModelInfo(BaseModel):
    """
    Нормализованное представление одной модели.
    LM Studio возвращает больше полей (object, owned_by и т.д.),
    но фронту нужен только id — остальное отбрасываем на границе backend/LM Studio,
    чтобы наш API-контракт не зависел от деталей формата LM Studio.
    """

    id: str


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
    lm_studio_available: bool