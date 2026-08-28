class LMStudioError(Exception):
    """Базовый класс для всех ошибок взаимодействия с LM Studio."""

    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(message)


class LMStudioUnreachableError(LMStudioError):
    """LM Studio не запущен или Local Server выключен — connection refused/DNS/etc."""

    def __init__(self, message: str = "Cannot connect to LM Studio"):
        super().__init__(message, code="LM_STUDIO_UNREACHABLE")


class LMStudioTimeoutError(LMStudioError):
    """LM Studio не ответил за отведённое время."""

    def __init__(self, message: str = "LM Studio did not respond in time"):
        super().__init__(message, code="LM_STUDIO_TIMEOUT")


class LMStudioHTTPError(LMStudioError):
    """LM Studio ответил, но с кодом ошибки (4xx/5xx)."""

    def __init__(self, status_code: int, message: str = "LM Studio returned an error"):
        self.status_code = status_code
        super().__init__(message, code="LM_STUDIO_HTTP_ERROR")


class MalformedResponseError(LMStudioError):
    """LM Studio ответил 200, но тело/чанк не соответствует ожидаемой схеме."""

    def __init__(self, message: str = "LM Studio returned an unexpected response format"):
        super().__init__(message, code="MALFORMED_RESPONSE")


class ModelNotFoundError(LMStudioError):
    """
    Клиент запросил model ID, которого нет среди моделей, реально
    загруженных в LM Studio на момент запроса.
    """

    def __init__(self, model_id: str):
        super().__init__(
            f"Model '{model_id}' is not currently loaded in LM Studio",
            code="MODEL_NOT_FOUND",
        )