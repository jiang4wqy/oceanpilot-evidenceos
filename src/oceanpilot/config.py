import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FeishuSettings:
    app_id: str = field(repr=False)
    app_secret: str = field(repr=False)
    verification_token: str = field(repr=False)
    encrypt_key: str = field(repr=False)
    callback_db_path: Path = Path("work/oceanpilot-feishu.db")
    demo_chat_id: str | None = None
    demo_merchant_ref: str | None = None

    @property
    def is_complete(self) -> bool:
        return all(
            type(value) is str and bool(value.strip())
            for value in (
                self.app_id,
                self.app_secret,
                self.verification_token,
                self.encrypt_key,
            )
        )

    @property
    def business_demo_is_complete(self) -> bool:
        return (
            type(self.demo_chat_id) is str
            and self.demo_chat_id == self.demo_chat_id.strip()
            and 0 < len(self.demo_chat_id) <= 100
            and type(self.demo_merchant_ref) is str
            and self.demo_merchant_ref == self.demo_merchant_ref.strip()
            and 0 < len(self.demo_merchant_ref) <= 128
        )


@dataclass(frozen=True, slots=True)
class Settings:
    db_path: Path
    host: str = "127.0.0.1"
    policy_version: str = "POLICY_V1"
    engine_version: str = "RULES_V1"
    feishu: FeishuSettings | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        credential_names = (
            "FEISHU_APP_ID",
            "FEISHU_APP_SECRET",
            "FEISHU_VERIFICATION_TOKEN",
            "FEISHU_ENCRYPT_KEY",
        )
        credential_values = tuple(os.getenv(name) for name in credential_names)
        feishu = None
        if all(value is not None and value.strip() for value in credential_values):
            app_id, app_secret, verification_token, encrypt_key = credential_values
            feishu = FeishuSettings(
                app_id=app_id,
                app_secret=app_secret,
                verification_token=verification_token,
                encrypt_key=encrypt_key,
                callback_db_path=Path(
                    os.getenv("OCEANPILOT_FEISHU_DB_PATH", "work/oceanpilot-feishu.db")
                ),
                demo_chat_id=os.getenv("OCEANPILOT_FEISHU_DEMO_CHAT_ID"),
                demo_merchant_ref=os.getenv("OCEANPILOT_FEISHU_DEMO_MERCHANT_REF"),
            )
        return cls(
            db_path=Path(os.getenv("OCEANPILOT_DB_PATH", "work/oceanpilot.db")),
            feishu=feishu,
        )
