from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Ollama settings
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_LLM_MODEL: str = "gemma3:4b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    # Storage settings
    CHROMA_PERSIST_DIRECTORY: str = "./chroma_db"
    UPLOAD_DIRECTORY: str = "./uploads"

    # Chunking settings
    CHUNK_SIZE: int = 1100
    CHUNK_OVERLAP: int = 150

    # Server settings
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    ANONYMIZED_TELEMETRY: bool = False
    OFFLINE_MODE_ONLY: bool = True
    REQUEST_TIMEOUT_SECONDS: float = 120.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def ensure_directories(self) -> None:
        Path(self.CHROMA_PERSIST_DIRECTORY).mkdir(parents=True, exist_ok=True)
        Path(self.UPLOAD_DIRECTORY).mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
