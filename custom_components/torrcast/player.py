"""One media player entity: the TV as torrcast sees it.

The buttons live in :mod:`custom_components.torrcast.remote` and the browse dialog in
:mod:`custom_components.torrcast.browsing`; what stays here is what the card *shows* -
the device it stands for and every field it draws out of the last snapshot.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .browsing import Browsing
from .const import DOMAIN
from .coordinator import Coordinator, TorrcastConfigEntry
from .remote import Remote

#: The five words of the contract and what Home Assistant calls the same thing.
#:
#: `torn` is not `idle`: the product still holds the show and says it will raise it
#: itself once the receiver comes back (`hass/motion.py`), and `idle` reads to a person
#: as nothing playing at all. `buffering` is the word Home Assistant already has for
#: "still on its way" - the same one `starting` uses below.
STATES: dict[str, MediaPlayerState] = {
    "idle": MediaPlayerState.IDLE,
    "starting": MediaPlayerState.BUFFERING,
    "playing": MediaPlayerState.PLAYING,
    "paused": MediaPlayerState.PAUSED,
    "torn": MediaPlayerState.BUFFERING,
}


def _device_name(tv: Any) -> str:
    """§4.1/§4.2 of the design want the receiver in the name, next to torrcast itself.

    HA turns this into both the card's title and the entity_id (``has_entity_name``
    with no entity-level name falls back to the device name); a bare receiver here
    is how ``media_player.192_168_1_90`` slipped past the spec.
    """
    return f"torrcast {tv}" if tv else "torrcast"


class Player(CoordinatorEntity[Coordinator], Remote, Browsing):
    """Shows what the serve reports and turns the buttons into its commands."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_media_content_type = MediaType.VIDEO
    #: `NEXT_TRACK` is not in this constant on purpose: the right arrow is only ever
    #: earned by a show that has a next episode to take, and that is a fact of the
    #: current snapshot, not a fact of the entity class (see `supported_features`
    #: below). Nothing else here is decided per snapshot.
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.SEEK
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.SEARCH_MEDIA
    )

    def __init__(self, coordinator: Coordinator, entry: TorrcastConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entry.unique_id or entry.entry_id
        snapshot = coordinator.data or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            manufacturer="torrcast",
            name=_device_name(snapshot.get("tv")),
            sw_version=snapshot.get("version"),
            configuration_url=coordinator.base_url,
        )

    @property
    def _snapshot(self) -> dict[str, Any]:
        """The last answer of the serve; empty is not a failure, it is just nothing yet."""
        return self.coordinator.data or {}

    @property
    def state(self) -> MediaPlayerState | None:
        return STATES.get(str(self._snapshot.get("state")))

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Two bits of the fixed set are actually a fact of the snapshot, not the class.

        The right arrow is added only when a next episode is there. `has_next` is the
        same field the serve keeps `null` for between shows and in the simple wait
        (`hass/payload.py`): the owner asked for the movie and the last episode of a
        series to lose the arrow, not for it to flicker off while nothing is decided
        yet. `False` alone drops the arrow; `True`, `None` and the field missing
        entirely (an older serve that predates it, same fallback shape as `named` in
        `hass/search_results.py`) all keep it, exactly as it always was.

        The power button is dropped on an empty screen: there is nothing playing to put
        out, and the owner asked for a single button there that reads the show back up
        instead (`Remote.async_media_play`). `state` reads `None` while the serve has
        not answered even once - the snapshot is empty, not idle - and the button stays
        claimed then, the same way it always did before this bit was split out.
        """
        base = self._attr_supported_features
        if self.state is MediaPlayerState.IDLE:
            base &= ~MediaPlayerEntityFeature.TURN_OFF
        if self._snapshot.get("has_next") is False:
            return base
        return base | MediaPlayerEntityFeature.NEXT_TRACK

    @property
    def media_title(self) -> str | None:
        snapshot = self._snapshot
        shown: str | None = snapshot.get("shown_as") or snapshot.get("title")
        return shown

    @property
    def media_image_url(self) -> str | None:
        """The poster, served by the serve itself and never by the site it came from.

        The serve downloads the picture and hands it out on its own route, so the
        address here always points at the LAN. Home Assistant never reaches out to
        Wikimedia or to a tracker for it: that traffic would go through the very
        network the whole product exists to step around.
        """
        path = self._snapshot.get("image")
        return f"{self.coordinator.base_url}{path}" if path else None

    @property
    def media_image_hash(self) -> str | None:
        """Fingerprint of the picture's own bytes, as the serve computed it.

        Without a hash Home Assistant caches the first picture against the entity and
        keeps drawing it over every later show. The default hash of the base class is
        taken from the URL, and the URL is what changes last here, so the serve says
        it outright.
        """
        digest = self._snapshot.get("image_hash")
        return str(digest) if digest else None

    @property
    def media_season(self) -> str | None:
        season = self._snapshot.get("season")
        return None if season is None else str(season)

    @property
    def media_episode(self) -> str | None:
        episode = self._snapshot.get("episode")
        return None if episode is None else str(episode)

    @property
    def media_position(self) -> int | None:
        position = self._snapshot.get("position")
        return None if position is None else int(position)

    @property
    def media_duration(self) -> int | None:
        duration = self._snapshot.get("duration")
        return None if duration is None else int(duration)

    @property
    def media_position_updated_at(self) -> datetime:
        marked: datetime = self.coordinator.position_at
        return marked

    @property
    def volume_level(self) -> float | None:
        volume = self._snapshot.get("volume")
        return None if volume is None else float(volume)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        snapshot = self._snapshot
        return {
            name: snapshot.get(name)
            for name in ("tv", "version", "warm", "disk_free", "last_error")
        }
