from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr


class FeishuUrlVerificationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    token: Annotated[StrictStr, Field(min_length=1, max_length=512)]
    type: Literal["url_verification"]
    challenge: Annotated[StrictStr, Field(min_length=1, max_length=512)]


class FeishuUrlVerificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    challenge: Annotated[StrictStr, Field(min_length=1, max_length=512)]
