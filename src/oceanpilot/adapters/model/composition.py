"""Composition root for the chargeback model provider (T10).

Builds the tiered ``ModelProvider`` the agent cluster uses when a live model is
enabled, honouring the security design:

* **LOW**  – non-sensitive: Claude directly.
* **MEDIUM** – redact PII, then Claude (``RedactingModelProvider``).
* **HIGH** – raw PII: a local/isolated model if one is configured
  (``OCEANPILOT_LOCAL_MODEL_ENDPOINT``); otherwise fall back to the redacting
  path so high-secrecy data is never sent in the clear.

Returns ``None`` when no ``ANTHROPIC_API_KEY`` is set, so the caller can fall
back to the offline provider. This keeps "Claude first, but keep the API pathway
pluggable": callers depend only on the ``ModelProvider`` port.
"""

import os

from oceanpilot.adapters.model.claude import ClaudeProvider
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
) -> ModelProvider | None:
    """Compose the tiered live provider, or ``None`` if no API key is configured.

    ``claude`` may be injected for tests; production constructs a ``ClaudeProvider``
    that reads credentials from the environment.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    external: ModelProvider = claude if claude is not None else ClaudeProvider()
    redacting = RedactingModelProvider(external, RegexRedactor())
    local = build_local_model_provider_from_env()
    return RoutingModelProvider(
        {
            SecurityTier.LOW: external,
            SecurityTier.MEDIUM: redacting,
            SecurityTier.HIGH: local if local is not None else redacting,
        }
    )
