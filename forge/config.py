"""Local-only settings. Model identities are deliberately not user-selectable."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

CHAT_MODEL = "qwen3:4b"
EMBED_MODEL = "nomic-embed-text"
PROMPT_VERSION = "grounded-v1"
INDEX_VERSION = "hybrid-500-75-v1"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    ollama_url: str = "http://127.0.0.1:11435"
    run_timeout: float = 120
    ingest_timeout: float = 180
    max_upload: int = 20 * 1024 * 1024

    def __post_init__(self) -> None:
        url = urlparse(self.ollama_url)
        if (
            url.scheme != "http"
            or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.username
            or url.password
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
        ):
            raise ValueError("Ollama must use an unauthenticated loopback HTTP address.")
        if self.run_timeout <= 0 or self.ingest_timeout <= 0:
            raise ValueError("Deadlines must be positive.")

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            Path(os.environ.get("FORGE_DATA_DIR", ".data")),
            os.environ.get("FORGE_OLLAMA_URL", "http://127.0.0.1:11435"),
        )
