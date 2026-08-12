from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from oceanpilot.adapters.feishu.security import FeishuVerificationError
from oceanpilot.api.cases import PROBLEM_RESPONSE
from oceanpilot.api.dependencies import FeishuRuntime, get_feishu_runtime
from oceanpilot.api.errors import (
    FeishuCallbackTooLarge,
    FeishuCallbackUnauthorized,
    FeishuInvalidCallback,
)
from oceanpilot.api.feishu_schemas import (
    FeishuUrlVerificationPayload,
    FeishuUrlVerificationResponse,
)

router = APIRouter(prefix="/api/v1/feishu")
_MAX_CALLBACK_BYTES = 65_536

_CALLBACK_PROBLEMS = {
    401: PROBLEM_RESPONSE,
    409: PROBLEM_RESPONSE,
    413: PROBLEM_RESPONSE,
    422: PROBLEM_RESPONSE,
    500: PROBLEM_RESPONSE,
    503: PROBLEM_RESPONSE,
}
_CALLBACK_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"type": "object"},
            }
        },
    }
}


async def _read_callback_body(request: Request) -> bytes:
    content_types = request.headers.getlist("content-type")
    if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != (
        "application/json"
    ):
        raise FeishuInvalidCallback()

    declared_lengths = request.headers.getlist("content-length")
    if len(declared_lengths) > 1:
        raise FeishuInvalidCallback()
    declared_length = None
    if declared_lengths:
        declared = declared_lengths[0]
        if (
            len(declared) > 20
            or not declared.isascii()
            or not declared.isdecimal()
        ):
            raise FeishuInvalidCallback()
        try:
            declared_length = int(declared)
        except ValueError:
            raise FeishuInvalidCallback() from None
        if declared_length > _MAX_CALLBACK_BYTES:
            raise FeishuCallbackTooLarge()

    chunks: list[bytes] = []
    actual_length = 0
    async for chunk in request.stream():
        actual_length += len(chunk)
        if actual_length > _MAX_CALLBACK_BYTES:
            raise FeishuCallbackTooLarge()
        chunks.append(chunk)
    if declared_length is not None and declared_length != actual_length:
        raise FeishuInvalidCallback()
    return b"".join(chunks)


async def _verified_payload(
    request: Request,
    runtime: FeishuRuntime,
) -> dict[str, object]:
    raw_body = await _read_callback_body(request)
    try:
        return runtime.verifier.verify(request.headers, raw_body)
    except FeishuVerificationError:
        raise FeishuCallbackUnauthorized() from None


@router.post(
    "/events",
    response_model=FeishuUrlVerificationResponse,
    responses=_CALLBACK_PROBLEMS,
    openapi_extra=_CALLBACK_OPENAPI,
)
async def receive_event(
    request: Request,
    runtime: Annotated[FeishuRuntime, Depends(get_feishu_runtime)],
) -> FeishuUrlVerificationResponse:
    payload = await _verified_payload(request, runtime)
    try:
        verification = FeishuUrlVerificationPayload.model_validate(payload)
    except ValidationError:
        raise FeishuInvalidCallback() from None
    return FeishuUrlVerificationResponse(challenge=verification.challenge)


@router.post(
    "/card-actions",
    responses=_CALLBACK_PROBLEMS,
    openapi_extra=_CALLBACK_OPENAPI,
)
async def receive_card_action(
    request: Request,
    runtime: Annotated[FeishuRuntime, Depends(get_feishu_runtime)],
) -> None:
    await _verified_payload(request, runtime)
    raise FeishuInvalidCallback()
