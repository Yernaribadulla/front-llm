from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Централизованная конфигурация приложения.
    Все значения читаются из .env, ничего не хардкодится в коде.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"

    # CORS: список origin'ов, разрешённых обращаться к backend.
    # Хранится в .env как строка через запятую, парсится в список.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Задел под этап 2 — уже читаем из .env, чтобы не переписывать
    # конфиг-слой, когда дойдём до LM Studio client.
    lm_studio_url: str = "http://localhost:1234/v1"
    lm_studio_timeout: int = 60

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """
    Кэшированный singleton настроек — .env читается один раз за жизнь процесса,
    а не на каждый запрос.
    """
    return Settings()