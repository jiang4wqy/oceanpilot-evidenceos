"""`ModelProvider` for a local / isolated model endpoint (T8, design §7.3/§8).

High-secrecy chargeback tasks (raw PII / transaction detail) must never leave the
trusted boundary, so they route to a self-hosted model instead of an external
API. This adapter speaks the widely-supported OpenAI-compatible
``/v1/chat/completions`` contract (vLLM, llama.cpp server, Ollama, LM Studio,
TGI), which lets the same code target most open-source serving stacks by config.

It implements the shared ``ModelProvider`` port, so ``RoutingModelProvider`` can
register it under ``SecurityTier.HIGH`` with no change to callers. The HTTP
transport is injectable, so tests exercise request building / response parsing /
failure handling without a network. Every failure raises the fixed
``ModelProviderError`` — endpoint, credentials and upstream detail never leak.
"""

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from oceanpilot.application.model_provider import (
    ModelMessage,
    ModelProviderError,
    ModelResult,
    TaskSpec,
    ToolCall,
    ToolSpec,
)

DEFAULT_LOCAL_MODEL = "local-isolated-model"


@dataclass(frozen=True, slots=True)
class LocalHttpRequest:
    method: Literal["POST"]
    url: str
    headers: tuple[tuple[str, str], ...]
    body: bytes
    timeout: float


@dataclass(frozen=True, slots=True)
class LocalHttpResponse:
    status_code: int
    body: bytes


def _urllib_transport(request: LocalHttpRequest) -> LocalHttpResponse:
    outgoing = Request(
        request.url,
        data=request.body,
        headers=dict(request.headers),
        method=request.method,
    )
    with urlopen(outgoing, timeout=request.timeout) as response:  # noqa: S310
        return LocalHttpResponse(status_code=response.status, body=response.read())


class LocalModelProvider:
    def __init__(
        self,
        *,
        endpoint: str,
        default_model: str = DEFAULT_LOCAL_MODEL,
        model_overrides: Mapping[str, str] | None = None,
        api_key: str | None = None,
        timeout: int | float = 60,
        transport: Callable[[LocalHttpRequest], LocalHttpResponse] | None = None,
    ) -> None:
        if type(endpoint) is not str or not endpoint:
            raise ValueError("endpoint must be a non-empty string")
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("endpoint must be an http(s) URL without credentials or fragment")
        if type(default_model) is not str or not default_model:
            raise ValueError("default_model must be a non-empty string")
        if api_key is not None and (type(api_key) is not str or not api_key):
            raise ValueError("api_key must be a non-empty string when provided")
        if type(timeout) not in (int, float) or timeout <= 0:
            raise ValueError("timeout must be a positive number")
        if transport is not None and not callable(transport):
            raise TypeError("transport must be callable")
        self._endpoint = endpoint
        self._default_model = default_model
        self._overrides = dict(model_overrides or {})
        self._api_key = api_key
        self._timeout = float(timeout)
        self._transport = transport or _urllib_transport

    def _model_for(self, task: TaskSpec) -> str:
        return self._overrides.get(task.kind, self._default_model)

    def complete(
        self,
        task: TaskSpec,
        messages: Sequence[ModelMessage],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
    ) -> ModelResult:
        payload: dict[str, object] = {
            "model": self._model_for(task),
            "messages": self._encode_messages(messages, system),
            "max_tokens": task.max_output_tokens,
            # Non-standard controls carried where OpenAI-compatible servers ignore
            # unknown keys; a server that honours effort/kind can read them here.
            "metadata": {
                "kind": task.kind,
                "effort": task.effort.value,
                "security_tier": task.security_tier.value,
            },
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": dict(tool.input_schema),
                    },
                }
                for tool in tools
            ]
            payload["tool_choice"] = "auto"

        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key}"

        request = LocalHttpRequest(
            method="POST",
            url=self._endpoint,
            headers=tuple(headers.items()),
            body=body,
            timeout=self._timeout,
        )
        try:
            response = self._transport(request)
        except Exception:
            raise ModelProviderError() from None
        if (
            type(response) is not LocalHttpResponse
            or type(response.status_code) is not int
            or type(response.body) is not bytes
            or not (200 <= response.status_code < 300)
        ):
            raise ModelProviderError()
        try:
            decoded = json.loads(response.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ModelProviderError() from None
        return self._to_result(decoded)

    @staticmethod
    def _encode_messages(
        messages: Sequence[ModelMessage],
        system: str | None,
    ) -> list[dict[str, str]]:
        encoded: list[dict[str, str]] = []
        if system is not None:
            encoded.append({"role": "system", "content": system})
        encoded.extend(
            {"role": message.role.value, "content": message.content} for message in messages
        )
        return encoded

    @staticmethod
    def _to_result(decoded: object) -> ModelResult:
        if not isinstance(decoded, dict):
            raise ModelProviderError()
        choices = decoded.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelProviderError()
        first = choices[0]
        if not isinstance(first, dict):
            raise ModelProviderError()
        message = first.get("message")
        if not isinstance(message, dict):
            raise ModelProviderError()

        content = message.get("content")
        if content is None:
            text = ""
        elif isinstance(content, str):
            text = content
        else:
            raise ModelProviderError()

        calls: list[ToolCall] = []
        raw_calls = message.get("tool_calls")
        if raw_calls is not None:
            if not isinstance(raw_calls, list):
                raise ModelProviderError()
            for raw_call in raw_calls:
                calls.append(LocalModelProvider._parse_tool_call(raw_call))

        stop_reason = first.get("finish_reason")
        model = decoded.get("model")
        return ModelResult(
            text=text,
            tool_calls=tuple(calls),
            stop_reason=stop_reason if isinstance(stop_reason, str) else None,
            model=model if isinstance(model, str) else None,
        )

    @staticmethod
    def _parse_tool_call(raw_call: object) -> ToolCall:
        if not isinstance(raw_call, dict):
            raise ModelProviderError()
        function = raw_call.get("function")
        if not isinstance(function, dict):
            raise ModelProviderError()
        name = function.get("name")
        arguments_raw = function.get("arguments")
        # OpenAI encodes tool arguments as a JSON *string*.
        if not isinstance(name, str) or not isinstance(arguments_raw, str):
            raise ModelProviderError()
        try:
            arguments = json.loads(arguments_raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ModelProviderError() from None
        if not isinstance(arguments, dict):
            raise ModelProviderError()
        call_id = raw_call.get("id")
        return ToolCall(
            call_id=call_id if isinstance(call_id, str) else "",
            name=name,
            arguments=arguments,
        )


def build_local_model_provider_from_env(
    *,
    transport: Callable[[LocalHttpRequest], LocalHttpResponse] | None = None,
) -> LocalModelProvider | None:
    """Composition-root helper: build the local provider from configuration.

    Returns ``None`` when no local endpoint is configured, so the composition
    root can fall back to an offline/default provider without special-casing.
    """
    endpoint = os.getenv("OCEANPILOT_LOCAL_MODEL_ENDPOINT")
    if not endpoint:
        return None
    return LocalModelProvider(
        endpoint=endpoint,
        default_model=os.getenv("OCEANPILOT_LOCAL_MODEL_NAME", DEFAULT_LOCAL_MODEL),
        api_key=os.getenv("OCEANPILOT_LOCAL_MODEL_API_KEY") or None,
        transport=transport,
    )
