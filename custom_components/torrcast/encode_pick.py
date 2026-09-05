"""The address one found picture travels to the card and back under.

A found picture travels back through ``async_play_media`` as a plain
``media_content_id`` string, and that string has to survive the round trip, carry both
the query and the number of the pick, and stay readable in a log line.
``torrcast://pick/<N>?q=<query>`` does all three: the scheme keeps it out of the way of a
bare-text query (still just the words a person would type, unmarked), the path carries
the pick number a human reads at a glance, and the query string carries the words that
found it. :func:`custom_components.torrcast.decode_pick.decode_pick` reads it back.
"""

from __future__ import annotations

from urllib.parse import quote

from .const import PICK_HOST, PICK_SCHEME


def encode_pick(query: str, pick: int) -> str:
    """The `media_content_id` of one result of `query`, numbered `pick`."""
    return f"{PICK_SCHEME}://{PICK_HOST}/{pick}?q={quote(query, safe='')}"
