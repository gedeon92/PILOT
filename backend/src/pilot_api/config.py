from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str | None = None

    session_days: int = 30
    invitation_days: int = 14

    @property
    def cookie_secure(self) -> bool:
        # En local et en test, l'API tourne en HTTP : un cookie « Secure » n'y serait pas renvoyé.
        return self.environment not in {"local", "test"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
