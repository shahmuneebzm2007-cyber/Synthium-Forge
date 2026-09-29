"""
Application configuration loaded from environment / .env file.
Single source of truth for all settings.
"""
import os
from pathlib import Path
from functools import lru_cache
from typing import Optional

from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load .env from backend/ directory
_backend_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(_backend_dir / ".env")


class AIConfig(BaseModel):
    """AI / LLM provider settings."""
    anthropic_keys: list[str] = Field(default_factory=list)
    openai_keys: list[str] = Field(default_factory=list)
    gemini_keys: list[str] = Field(default_factory=list)
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    timeout: int = 20
    max_retries: int = 2
    offline: bool = False


class StorageConfig(BaseModel):
    """File / artifact storage settings."""
    data_dir: Path = Path("./data")
    artifact_ttl_hours: int = 1
    max_upload_mb: int = 200


class ServerConfig(BaseModel):
    """Server / runtime settings."""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    project_salt: str = "synthgen-hackathon-2026"


class AppConfig(BaseModel):
    """Root application configuration."""
    ai: AIConfig = Field(default_factory=AIConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)


def _parse_key_list(env_var: str) -> list[str]:
    """Parse comma-separated API keys from an env var, filtering blanks."""
    raw = os.getenv(env_var, "")
    return [k.strip() for k in raw.split(",") if k.strip()]


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Load and cache the application config. Called once at startup."""
    ai = AIConfig(
        anthropic_keys=_parse_key_list("ANTHROPIC_API_KEYS"),
        openai_keys=_parse_key_list("OPENAI_API_KEYS"),
        gemini_keys=_parse_key_list("GEMINI_API_KEYS"),
        provider=os.getenv("LLM_PROVIDER", "anthropic"),
        model=os.getenv("LLM_MODEL", "claude-sonnet-4-20250514"),
        timeout=int(os.getenv("LLM_TIMEOUT", "20")),
        max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        offline=os.getenv("OFFLINE", "0") == "1",
    )
    storage = StorageConfig(
        data_dir=Path(os.getenv("DATA_DIR", "./data")),
        artifact_ttl_hours=int(os.getenv("ARTIFACT_TTL_HOURS", "1")),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "200")),
    )
    server = ServerConfig(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        debug=os.getenv("DEBUG", "1") == "1",
        project_salt=os.getenv("PROJECT_SALT", "synthgen-hackathon-2026"),
    )
    cfg = AppConfig(ai=ai, storage=storage, server=server)
    # Ensure data directories exist
    cfg.storage.data_dir.mkdir(parents=True, exist_ok=True)
    (cfg.storage.data_dir / "uploads").mkdir(exist_ok=True)
    (cfg.storage.data_dir / "artifacts").mkdir(exist_ok=True)
    (cfg.storage.data_dir / "projects").mkdir(exist_ok=True)
    return cfg
