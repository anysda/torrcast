"""Names shared by the torrcast integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "torrcast"
#: The serve listens here; the port is part of the contract, not a preference.
DEFAULT_PORT: Final = 8479
#: A show moves, so it is polled often; an idle box is asked six times more rarely.
SCAN_INTERVAL_SHOWING: Final = timedelta(seconds=5)
SCAN_INTERVAL_IDLE: Final = timedelta(seconds=30)
#: The one state that means the picture is moving right now; the slider counts on it.
PLAYING: Final = "playing"
#: States that mean something is on the screen right now.
SHOWING_STATES: Final = frozenset({"starting", PLAYING, "paused"})
#: Volume is absolute on the wire, so a step is added here and sent as a level.
VOLUME_STEP: Final = 0.05
#: Seconds; the serve answers from the local network and has no reason to be slow.
REQUEST_TIMEOUT: Final = 10
#: Seconds; a search walks out to the indexers, not just the local network.
#:
#: Measured on the stand: a cold search answered in 11.0 s while the shared
#: :data:`REQUEST_TIMEOUT` (10 s) was already spent, and the entry field told a person
#: the search failed while the serve was still working on it. The serve itself waits up
#: to 150 s for one stuck indexer before it gives up
#: (``torrcast.adapters.prowlarr.prowlarr_api.TIMEOUT``); a search timeout shorter than
#: that can cut off an answer the serve would still have delivered. Margin is added on
#: top of that ceiling, not on top of the one cold measurement.
SEARCH_REQUEST_TIMEOUT: Final = 160
#: Seconds; a poster of a search hit may still be on its way from the serve, and the
#: serve holds that one request for a few seconds rather than answering "no picture"
#: (`hass/hit_posters.py`). The wait here has to outlast that hold, or the picture would
#: be dropped by the very side that asked for it.
POSTER_REQUEST_TIMEOUT: Final = 15
#: Scheme and host of a picked search hit; anything else in `media_content_id` is a
#: bare query, exactly as `async_play_media` has always treated it.
PICK_SCHEME: Final = "torrcast"
PICK_HOST: Final = "pick"
#: The three browse nodes: an empty root and its two children, menu first. The titles
#: are the two words the owner asked for, verbatim - a person reads them on the field.
#: Only the prefix of the instant id is Home Assistant's; the word past it is ours and
#: comes back untouched.
ROOT_ID: Final = ""
MENU_ID: Final = "menu"
INSTANT_TITLE: Final = "instant"
INSTANT_ID: Final = f"media-source://tts/{INSTANT_TITLE}"
#: Where the dialog puts what a person typed before handing the id back for playing.
MESSAGE_FIELD: Final = "message"
