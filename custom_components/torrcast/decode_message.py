"""What a person typed into the instant field, read off the id that came back."""

from __future__ import annotations

from urllib.parse import parse_qs

from .const import INSTANT_ID, MESSAGE_FIELD


def decode_message(media_content_id: str) -> str | None:
    """What a person typed into the instant field; `None` if it came from elsewhere.

    The dialog plays the node's own id with the typed words appended as `message`
    (`_ttsClicked` in the shipped `55397.*.js`), so the words arrive here as a query
    string and nothing else about the id changes.
    """
    node_id, _, typed = media_content_id.partition("?")
    if node_id != INSTANT_ID:
        return None
    return parse_qs(typed).get(MESSAGE_FIELD, [""])[0].strip()
