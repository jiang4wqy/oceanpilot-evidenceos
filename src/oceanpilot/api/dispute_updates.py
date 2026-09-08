"""Long-poll changes for the current OP workspace or merchant-owned case scope."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from oceanpilot.api.disputes import COMMON_PROBLEMS, PROBLEM_RESPONSE, Identity

router = APIRouter(
    tags=["OceanPilot V2"],
    responses={
        **COMMON_PROBLEMS,
        403: PROBLEM_RESPONSE,
        404: PROBLEM_RESPONSE,
        409: PROBLEM_RESPONSE,
        503: PROBLEM_RESPONSE,
    },
)


@router.get("/api/v2/updates")
async def dispute_updates(
    request: Request,
    response: Response,
    identity: Identity,
    cursor: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
    case_id: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    timeout: Annotated[float, Query(ge=0, le=20, allow_inf_nan=False)] = 20,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "X-Demo-Role, X-Demo-Actor, X-Demo-Merchant"
    return await request.app.state.dispute_updates.poll(
        identity,
        cursor=cursor,
        case_id=case_id,
        timeout=timeout,
        disconnected=request.is_disconnected,
    )
