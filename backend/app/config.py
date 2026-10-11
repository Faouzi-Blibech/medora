import logging
import secrets
from functools import lru_cache
from typing import Literal

from pydantic import PrivateAttr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("ward.config")

# Public defaults (also in .env.example): kept as constants so they can be detected.
DEFAULT_JWT_SECRET = "change-me-to-a-long-random-string"  # NOSONAR
DEFAULT_N8N_EVENT_SECRET = "change-me-event"  # NOSONAR
DEFAULT_N8N_CALLBACK_SECRET = "change-me-callback"  # NOSONAR
DEFAULT_MINIO_ROOT_PASSWORD = "wardminio123"  # NOSONAR
DEFAULT_MQTT_PASSWORD = "change-me-mqtt"  # NOSONAR: demo broker account, see infra/mosquitto
DEFAULT_SEED_PASSWORD = "ward1234"  # NOSONAR: documented demo default for synthetic data
DEFAULT_DB_CREDENTIALS = "ward:ward@"
MIN_JWT_SECRET_LEN = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    # demo: weak defaults only warn; prod: the API and seed refuse to start on them
    ward_env: Literal["demo", "prod"] = "demo"
    _jwt_was_insecure: bool = PrivateAttr(default=False)

    database_url: str = "postgresql+psycopg://ward:ward@localhost:5432/ward"

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    # the backend's broker account (infra/mosquitto/acl); compose sets both from MQTT_BACKEND_USERNAME/_PASSWORD
    mqtt_username: str = "ward-backend"
    mqtt_password: str = DEFAULT_MQTT_PASSWORD

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_expire_hours: int = 8
    hospital_name: str = "Ward Hospital"  # GET /hospital: this install's hospital (one install per hospital)
    # health watch: the hospital's city for the weather-health alerts (Open-Meteo, no key) and the news feeds
    hospital_city: str = "Tunis"
    hospital_lat: float = 36.8065
    hospital_lon: float = 10.1815
    health_watch_offline: bool = False  # true: no outside calls (offline demo)
    health_watch_demo: str = ""  # heatwave | dust | cold: inject a labelled demo scenario into the forecast
    # comma-separated; the proxy domain in the internet profile
    web_origin: str = "http://localhost:3000"
    web_url: str = "http://localhost:3000"  # links in pushes (WEB_URL)
    bcrypt_rounds: int = 12
    # demo password of the synthetic seed accounts (api.md); set SEED_PASSWORD for any other deployment
    seed_password: str = DEFAULT_SEED_PASSWORD  # overridable via SEED_PASSWORD

    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "ward"
    minio_root_password: str = DEFAULT_MINIO_ROOT_PASSWORD
    minio_bucket: str = "ward-docs"

    n8n_webhook_url: str = "http://localhost:5678/webhook/ward-events"
    n8n_event_secret: str = DEFAULT_N8N_EVENT_SECRET
    n8n_callback_secret: str = DEFAULT_N8N_CALLBACK_SECRET

    llm_provider: str = "none"  # none | groq | local (optional, open models only)
    groq_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"
    llm_local_base_url: str = "http://localhost:11434"
    llm_local_model: str = "qwen2.5:7b-instruct"
    llm_timeout_s: float = 15.0
    vision_provider: str = "none"  # none | local — radiograph images never go to a hosted API
    llm_vision_model: str = "qwen3-vl:4b"
    llm_vision_timeout_s: float = 180.0
    radiology_report_lang: str = "fr"  # fr | en

    @model_validator(mode="after")
    def _harden_jwt_secret(self) -> "Settings":
        if self.jwt_secret == DEFAULT_JWT_SECRET or len(self.jwt_secret) < MIN_JWT_SECRET_LEN:
            self._jwt_was_insecure = True
            if self.ward_env == "prod":
                raise RuntimeError(
                    f"JWT_SECRET is the default or shorter than {MIN_JWT_SECRET_LEN} chars; refusing to start with WARD_ENV=prod"
                )
            # One random value per process: get_settings() is lru_cached and the API runs as a single
            # uvicorn process, so every token check sees the same secret. With several workers they would differ.
            self.jwt_secret = secrets.token_urlsafe(48)
            log.warning(
                "JWT_SECRET is the default or too short: using a random secret, so tokens will not survive a restart. "
                "Set JWT_SECRET (>= %d chars) in .env, e.g. python -c \"import secrets; print(secrets.token_urlsafe(48))\"",
                MIN_JWT_SECRET_LEN,
            )
        return self


def insecure_defaults(settings: Settings) -> list[str]:
    """Names of settings still at a known public default."""
    found = []
    if settings._jwt_was_insecure:  # judged on the input, before the random replacement
        found.append("jwt_secret")
    if settings.n8n_event_secret == DEFAULT_N8N_EVENT_SECRET:
        found.append("n8n_event_secret")
    if settings.n8n_callback_secret == DEFAULT_N8N_CALLBACK_SECRET:
        found.append("n8n_callback_secret")
    if settings.minio_root_password == DEFAULT_MINIO_ROOT_PASSWORD:
        found.append("minio_root_password")
    if settings.mqtt_password == DEFAULT_MQTT_PASSWORD:
        found.append("mqtt_password")
    if settings.seed_password == DEFAULT_SEED_PASSWORD:
        found.append("seed_password")
    if DEFAULT_DB_CREDENTIALS in settings.database_url:
        found.append("database_url")
    return found


def check_secrets(settings: Settings) -> None:
    """prod: raise on default secrets; demo: log one warning."""
    names = insecure_defaults(settings)
    if not names:
        return
    if settings.ward_env == "prod":
        raise RuntimeError(f"WARD_ENV=prod but these settings are still at their defaults: {', '.join(names)}")
    log.warning("Default secrets in use (fine for the offline demo, never for a real deployment): %s", ", ".join(names))


@lru_cache
def get_settings() -> Settings:
    return Settings()
