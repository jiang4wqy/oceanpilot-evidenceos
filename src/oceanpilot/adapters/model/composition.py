"""Composition root for the chargeback model provider (T10).

Builds the tiered ``ModelProvider`` the agent cluster uses when a live model is
enabled, honouring the security design:

* **LOW**  – non-sensitive: the selected external provider directly.
* **MEDIUM** – redact PII, then the selected external provider
  (``RedactingModelProvider``).
* **HIGH** – raw PII: a local/isolated model if one is configured
  (``OCEANPILOT_LOCAL_MODEL_ENDPOINT``); otherwise fall back to the redacting
  path so high-secrecy data is never sent in the clear.

Returns ``None`` when the selected provider has no API key, so the caller can
fall back to the offline provider. Callers depend only on the ``ModelProvider``
port and do not import vendor adapters.
"""

import os

from oceanpilot.adapters.model.claude import ClaudeProvider
from oceanpilot.adapters.model.deepseek import build_deepseek_model_provider_from_env
from oceanpilot.adapters.model.local import build_local_model_provider_from_env
from oceanpilot.adapters.redaction import RegexRedactor
from oceanpilot.application.model_provider import (
    ModelProvider,
    RoutingModelProvider,
    SecurityTier,
)
from oceanpilot.application.redaction import RedactingModelProvider


def build_chargeback_model_provider(
    *,
    claude: ModelProvider | None = None,
    deepseek: ModelProvider | None = None,
) -> ModelProvider | None:
    """Compose the tiered live provider, or ``None`` if no API key is configured.

    Provider arguments may be injected for tests. Production selects Claude or
    DeepSeek through ``OCEANPILOT_MODEL_PROVIDER`` and reads credentials only
    from the environment.
    """
    provider_name = os.getenv("OCEANPILOT_MODEL_PROVIDER", "claude").strip().lower()
    if provider_name == "claude":
        if not os.getenv("ANTHROPIC_API_KEY"):
            return None
        external: ModelProvider = claude if claude is not None else ClaudeProvider()
    elif provider_name == "deepseek":
        external = deepseek if deepseek is not None else build_deepseek_model_provider_from_env()
        if external is None:
            return None
    else:
        raise ValueError("OCEANPILOT_MODEL_PROVIDER must be 'claude' or 'deepseek'")
    redacting = RedactingModelProvider(external, RegexRedactor())
    local = build_local_model_provider_from_env()
    return RoutingModelProvider(
        {
            SecurityTier.LOW: external,
            SecurityTier.MEDIUM: redacting,
            SecurityTier.HIGH: local if local is not None else redacting,
        }
    )
