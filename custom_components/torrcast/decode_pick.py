"""Reads back the query and the pick number an id of a found picture carries."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from .const import PICK_HOST, PICK_SCHEME


def decode_pick(media_content_id: str) -> tuple[str, int] | None:
    """The query and pick number a `media_content_id` names; `None` for a bare query."""
    parsed = urlsplit(media_content_id)
    if parsed.scheme != PICK_SCHEME or parsed.netloc != PICK_HOST:
        return None
    number = parsed.path.lstrip("/")
    if not number.isdigit():
        return None
    query = parse_qs(parsed.query).get("q", [""])[0]
    return query, int(number)
