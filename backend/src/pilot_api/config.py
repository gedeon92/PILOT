from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str | None = None

    session_days: int = 30
    invitation_days: int = 14
    # Phase de test : fichiers stockés dans Neon (1 Go gratuit) et relayés par Vercel.
    max_upload_mb: float = 4

    # Rappels par e-mail (Brevo). Sans clé, les alertes restent visibles dans l'application.
    brevo_api_key: str | None = None
    mail_sender_email: str | None = None
    mail_sender_name: str = "PILOT"
    app_base_url: str = "https://pilot-beta-swart.vercel.app"
    # Clé partagée avec la tâche planifiée GitHub qui déclenche les rappels.
    cron_secret: str | None = None

    @property
    def cookie_secure(self) -> bool:
        # En local et en test, l'API tourne en HTTP : un cookie « Secure » n'y serait pas renvoyé.
        return self.environment not in {"local", "test"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
