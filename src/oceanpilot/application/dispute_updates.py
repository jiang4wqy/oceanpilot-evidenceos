"""Read-only long polling over durable, scoped dispute and Agent change positions."""

import asyncio
import base64
import binascii
import json
from collections.abc import Awaitable, Callable
from hashlib import sha256
from math import isfinite
from time import monotonic
from typing import Protocol

from oceanpilot.application.disputes import DisputeService
from oceanpilot.domain.dispute import DisputeError, require, text_field


class DisputeUpdateReader(Protocol):
    def read(self, identity: dict, case_id: str | None, position: dict | None) -> dict: ...


class DisputeUpdatesService:
    def __init__(
        self, reader: DisputeUpdateReader, *, poll_interval: float = 0.35, read_timeout: float = 2
    ) -> None:
        require(
            type(poll_interval) in (int, float)
            and isfinite(poll_interval)
            and 0 < poll_interval <= 1,
            "INVALID_INPUT",
            "Invalid polling interval",
            422,
        )
        self.reader = reader
        self.poll_interval = poll_interval
        require(
            type(read_timeout) in (int, float) and isfinite(read_timeout) and 0 < read_timeout <= 2,
            "INVALID_INPUT",
            "Invalid read timeout",
            422,
        )
        self.read_timeout = read_timeout

    @staticmethod
    def _scope(identity: dict, case_id: str | None) -> str:
        scope = [
            identity["role"],
            identity["actor_id"],
            identity["merchant_id"] if identity["role"] == "MERCHANT" else None,
            case_id,
        ]
        return sha256(json.dumps(scope, ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def _decode(cursor: str | None) -> dict | None:
        if cursor is None:
            return None
        require(
            isinstance(cursor, str) and 0 < len(cursor) <= 2048,
            "INVALID_CURSOR",
            "Invalid update cursor",
            422,
        )
        try:
            raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            decoded = json.loads(raw)
            require(
                isinstance(decoded, dict) and set(decoded) == {"v", "scope", "epoch", "positions"},
                "INVALID_CURSOR",
                "Invalid update cursor",
                422,
            )
            require(
                type(decoded["v"]) is int and decoded["v"] == 1,
                "INVALID_CURSOR",
                "Unsupported update cursor version",
                422,
            )
            require(
                all(
                    isinstance(decoded[key], str) and len(decoded[key]) == 64
                    for key in ("scope", "epoch")
                ),
                "INVALID_CURSOR",
                "Invalid update cursor scope",
                422,
            )
            positions = decoded["positions"]
            require(
                isinstance(positions, dict)
                and set(positions) == {"case", "agent", "conversation"}
                and all(
                    type(value) is int and 0 <= value <= 2**63 - 1 for value in positions.values()
                ),
                "INVALID_CURSOR",
                "Invalid update positions",
                422,
            )
            return decoded
        except (ValueError, UnicodeError, binascii.Error, TypeError, RecursionError) as exc:
            raise DisputeError("INVALID_CURSOR", "Invalid update cursor", 422) from exc

    @staticmethod
    def _encode(scope: str, snapshot: dict) -> str:
        payload = {
            "v": 1,
            "scope": scope,
            "epoch": snapshot["epoch"],
            "positions": snapshot["positions"],
        }
        return (
            base64.urlsafe_b64encode(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            )
            .decode()
            .rstrip("=")
        )

    async def poll(
        self,
        identity: dict,
        *,
        cursor: str | None = None,
        case_id: str | None = None,
        timeout: float = 20,
        disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> dict:
        identity = DisputeService._identity(identity)
        require(
            type(timeout) in (int, float) and isfinite(timeout) and 0 <= timeout <= 20,
            "INVALID_TIMEOUT",
            "Update timeout must be between 0 and 20 seconds",
            422,
        )
        if case_id is not None:
            case_id = text_field({"case_id": case_id}, "case_id", limit=100)
        previous = self._decode(cursor)
        scope = self._scope(identity, case_id)
        if previous is not None and previous["scope"] != scope:
            # A cursor is a position, never authorization. Scope changes require a fresh baseline.
            previous = None
        deadline = monotonic() + timeout
        while True:
            if disconnected is not None and await disconnected():
                raise asyncio.CancelledError
            try:
                # Also bound executor-queue delays under many simultaneous client connections.
                snapshot = await asyncio.wait_for(
                    asyncio.to_thread(self.reader.read, identity, case_id, previous),
                    timeout=self.read_timeout,
                )
            except TimeoutError as exc:
                raise DisputeError(
                    "UPDATES_UNAVAILABLE", "Dispute updates are temporarily unavailable", 503
                ) from exc
            remaining = deadline - monotonic()
            changed = bool(snapshot["changes"])
            if snapshot["reset"] or changed or remaining <= 0:
                return {
                    "cursor": self._encode(scope, snapshot),
                    "changed_case_ids": [item["case_id"] for item in snapshot["changes"]],
                    "changes": snapshot["changes"],
                    "reset": snapshot["reset"],
                    "timed_out": not snapshot["reset"] and not changed,
                }
            await asyncio.sleep(min(self.poll_interval, remaining))
