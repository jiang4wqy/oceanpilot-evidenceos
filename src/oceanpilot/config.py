import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    db_path: Path
    host: str = "127.0.0.1"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(db_path=Path(os.getenv("OCEANPILOT_DB_PATH", "work/oceanpilot.db")))
