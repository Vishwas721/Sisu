import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

@dataclass
class Config:
    # Database settings
    DB_HOST: str = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "leads_pipeline")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

    # Ollama settings
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    # Off by default: the personalized templates are reliable; small local models drift
    USE_LLM_DRAFTS: bool = os.getenv("USE_LLM_DRAFTS", "false").lower() in ("true", "1", "yes")

    # Outreach sender details (address is required in commercial email under CAN-SPAM)
    SENDER_NAME: str = os.getenv("SENDER_NAME", "Vishwas")
    SENDER_ADDRESS: str = os.getenv("SENDER_ADDRESS", "")

    # Discovery settings (optional: without a key only OpenStreetMap is used)
    GOOGLE_PLACES_API_KEY: str = os.getenv("GOOGLE_PLACES_API_KEY", "")

    # Most new leads saved per calendar day across all runs (0 = no limit). Keep it near
    # what you can actually email; a new sending domain should start around 10-20/day
    DAILY_LEAD_CAP: int = int(os.getenv("DAILY_LEAD_CAP", "30"))

    # Scraper settings
    PLAYWRIGHT_HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() in ("true", "1", "yes")
    PAGE_TIMEOUT_MS: int = int(os.getenv("PAGE_TIMEOUT_MS", "30000"))

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

config = Config()

# ==============================================================================
# Target cities and niches live in targets.json so the dashboard can share them.
# TARGET_CITIES maps name -> Overpass bounding box "South,West,North,East".
# ==============================================================================
TARGETS_FILE = Path(__file__).parent / "targets.json"
_targets = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))

TARGET_NICHES: List[str] = _targets["niches"]
TARGET_CITIES: Dict[str, str] = {
    name: ",".join(f"{c:g}" for c in bbox) for name, bbox in _targets["cities"].items()
}
