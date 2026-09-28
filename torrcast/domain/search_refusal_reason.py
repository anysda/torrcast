"""A search refusal reason the page can render."""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.domain.json_value import JsonValue


@dataclass(frozen=True, slots=True)
class SearchRefusalReason:
    """A page-catalog key and the values it needs."""

    key: str
    values: dict[str, JsonValue]

    def json(self) -> dict[str, JsonValue]:
        """Return the response object read by the page."""
        return {"key": self.key, "values": self.values}


__all__ = ["SearchRefusalReason"]
