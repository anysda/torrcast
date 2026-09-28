"""Private JSON reason for a named search refusal."""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.domain.json_value import JsonValue


@dataclass(frozen=True, slots=True)
class _SearchReason:
    key: str
    values: dict[str, JsonValue]

    def json(self) -> dict[str, JsonValue]:
        return {"key": self.key, "values": self.values}
