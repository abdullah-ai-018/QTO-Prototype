"""Central application configuration.

All runtime configuration is sourced from environment variables (via a
`.env` file in development). Nothing here hardcodes an environment-specific
value — switching from SQLite to PostgreSQL, for example, is a single
DATABASE_URL change with zero code changes anywhere else in the app.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "Protake"
    environment: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # --- Security ---
    secret_key: str = "change-this-to-a-long-random-string-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # --- Database ---
    database_url: str = "sqlite:///./storage/protake.db"

    # --- CORS ---
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    # --- Storage ---
    storage_dir: str = "./storage"
    upload_dir: str = "./storage/uploads"
    thumbnail_dir: str = "./storage/thumbnails"
    report_dir: str = "./storage/reports"
    max_upload_size_mb: int = 100

    # --- AI Assistant ---
    # DeepSeek is the active provider (see assistant_service.py) — its API
    # is OpenAI-compatible, called directly via httpx rather than pulling
    # in a new SDK dependency. anthropic_api_key/anthropic_model are kept
    # as a documented fallback path, not currently wired to anything; set
    # DEEPSEEK_API_KEY to empty and ANTHROPIC_API_KEY to a real key to
    # switch back without further code changes to config.py.
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5-20250929"

    # --- AI Validation ---
    yolo_model_path: str = "yolo11n.pt"
    yolo_secondary_model_path: str = ""
    yolo_furniture_model_path: str = ""
    yolo_roomtype_model_path: str = ""
    yolo_cabinet_model_path: str = ""
    sam_model_path: str = "sam2.1_b.pt"
    ai_validation_enabled: bool = True

    # --- OCR ---
    ocr_enabled: bool = True
    ocr_lang: str = "en"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def ensure_storage_dirs(self) -> None:
        for path in (self.storage_dir, self.upload_dir, self.thumbnail_dir, self.report_dir):
            Path(path).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_storage_dirs()
    return settings
