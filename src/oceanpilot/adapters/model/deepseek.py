"""DeepSeek adapter built on the existing OpenAI-compatible transport."""

import os
from collections.abc import Callable

from oceanpilot.adapters.model.local import (
    LocalHttpRequest,
    LocalHttpResponse,
    LocalModelProvider,
)

DEFAULT_DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


def _chat_completions_endpoint(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def build_deepseek_model_provider_from_env(
    *,
    transport: Callable[[LocalHttpRequest], LocalHttpResponse] | None = None,
) -> LocalModelProvider | None:
    """Build a DeepSeek provider, or ``None`` when no API key is configured."""

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None
    return LocalModelProvider(
        endpoint=_chat_completions_endpoint(
            os.getenv("DEEPSEEK_API_BASE", DEFAULT_DEEPSEEK_API_BASE)
        ),
        default_model=os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL),
        api_key=api_key,
        include_metadata=False,
        transport=transport,
    )
