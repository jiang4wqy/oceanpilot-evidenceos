import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FeishuSettings:
    app_id: str
    app_secret: str
    verification_token: str
    encrypt_key: str
    db_path: Path


@dataclass(frozen=True, slots=True)
class Settings:
    db_path: Path
    host: str = "127.0.0.1"
    policy_version: str = "POLICY_V1"
    engine_version: str = "RULES_V1"
    feishu: FeishuSettings | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        db_path = Path(os.getenv("OCEANPILOT_DB_PATH", "work/oceanpilot.db"))
        return cls(db_path=db_path, feishu=_feishu_from_env(db_path))


def _feishu_from_env(core_db_path: Path) -> FeishuSettings | None:
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    verification_token = os.getenv("FEISHU_VERIFICATION_TOKEN")
    encrypt_key = os.getenv("FEISHU_ENCRYPT_KEY")
    if not (app_id and app_secret and verification_token and encrypt_key):
        return None
    default_feishu_db = core_db_path.parent / "oceanpilot-feishu.db"
    db_path = Path(os.getenv("OCEANPILOT_FEISHU_DB_PATH", str(default_feishu_db)))
    return FeishuSettings(
        app_id=app_id,
        app_secret=app_secret,
        verification_token=verification_token,
        encrypt_key=encrypt_key,
        db_path=db_path,
    )
