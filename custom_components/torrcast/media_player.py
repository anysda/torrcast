"""One media player entity: the TV as torrcast sees it."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    SearchMedia,
    SearchMediaQuery,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .browse import browse, decode_message, decode_pick, search_media
from .const import DOMAIN, VOLUME_STEP
from .coordinator import TorrcastConfigEntry, TorrcastCoordinator

_LOGGER = logging.getLogger(__name__)

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


async def async_setup_entry(
    # The platform contract names `hass` first even where the body has no use for it;
    # dropping the parameter would break the call, not tidy it up.
    hass: HomeAssistant,  # noqa: ARG001
    entry: TorrcastConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """One serve is one TV, so the platform adds exactly one entity."""
    _LOGGER.debug("adding the player of %s", entry.runtime_data.base_url)
    async_add_entities([TorrcastPlayer(entry.runtime_data, entry)])


class TorrcastPlayer(CoordinatorEntity[TorrcastCoordinator], MediaPlayerEntity):
    """Shows what the serve reports and turns the buttons into its commands."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_media_content_type = MediaType.VIDEO
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.SEEK
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.SEARCH_MEDIA
    )

    def __init__(self, coordinator: TorrcastCoordinator, entry: TorrcastConfigEntry) -> None:
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
        return self.coordinator.taken_at

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

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play a plain query as ever, one exact hit of a prior search, or a typed name.

        `media_id` is the same free text a person would hand `cast` on the terminal,
        unless it names a search hit (`browse.decode_pick`) or carries what a person
        typed into the instant field (`browse.decode_message`); the content type is not
        looked at in any of the three cases, and neither is the `announce` the browse
        dialog adds to a message of its own accord.
        """
        _LOGGER.debug("play %s (type %s, extras %s)", media_id, media_type, kwargs)
        typed = decode_message(media_id)
        if typed is not None:
            await self.coordinator.async_play(typed)
            return
        picked = decode_pick(media_id)
        if picked is None:
            await self.coordinator.async_play(media_id)
            return
        query, pick = picked
        await self.coordinator.async_play(query, pick=pick)

    async def async_browse_media(
        self,
        # The platform contract carries the content type even where the tree does not
        # branch by it (see `browse.py`); dropping the parameter would break the call.
        media_content_type: MediaType | str | None = None,  # noqa: ARG002
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Root, and its one child that carries the search field (see `browse.py`)."""
        return browse(media_content_id)

    async def async_search_media(self, query: SearchMediaQuery) -> SearchMedia:
        """Ask the serve for `query`, the picture a bare `POST /api/play` takes first.

        Which picture that is the serve says with a `default` flag on the hit, and
        `browse.search_media` moves it to the front: Home Assistant's own voice handler
        plays `result[0]`, so first has to mean taken.

        Only the `menu` node carries a search field at all (see `browse.py`), so the
        answer is always that node's full list; a voice command reaching the same place
        without a node of its own gets the same list.

        A blank query is answered with nothing rather than sent on: the serve's own
        `no_query` refusal exists for `/api/play`, not for a search box a person has
        not typed into yet.
        """
        text = query.search_query.strip()
        if not text:
            return search_media(text, [])
        hits = await self.coordinator.async_search(text)
        return search_media(text, hits, self.get_browse_image_url)

    async def async_get_browse_image(
        self,
        # The proxy route carries the hit itself as well as the name of its picture; the
        # name alone is enough here, and dropping the two would break the call.
        media_content_type: MediaType | str,  # noqa: ARG002
        media_content_id: str,  # noqa: ARG002
        media_image_id: str | None = None,
    ) -> tuple[bytes | None, str | None]:
        """The poster of one hit, fetched by Home Assistant itself, never by the browser.

        `get_browse_image_url` (used above) points a hit's thumbnail at Home Assistant's
        own proxy route, which lands here on the server side with the name the serve gave
        the picture in `media_image_id`. So the picture crosses two hops that both already
        exist: browser to Home Assistant, then Home Assistant to the serve on the local
        network - the same pair the card's own picture crosses. Neither hop leaves the
        house, and the query and pick in `media_content_id` are not needed to name a
        picture the serve has already put a name on.
        """
        if not media_image_id:
            return None, None
        return await self.coordinator.async_poster(media_image_id)

    async def async_media_play(self) -> None:
        await self.coordinator.async_control("toggle")

    async def async_media_pause(self) -> None:
        await self.coordinator.async_control("toggle")

    async def async_media_play_pause(self) -> None:
        await self.coordinator.async_control("toggle")

    async def async_media_stop(self) -> None:
        await self.coordinator.async_control("stop")

    async def async_turn_off(self) -> None:
        """The power button of the card: put the show out and let the receiver go.

        Off means the show, not the mains: the product has no way to unplug a television
        and does not pretend to. It is the same `stop` the console and the bot send, so
        the button opens no new road outwards - `TURN_ON` is deliberately not claimed
        next to it, because there would be nothing for it to raise.

        An already idle player is silent about it. `stop` on an empty screen is the
        serve's `nothing_playing` refusal, and reading "torrcast has nothing on the
        screen right now" after pressing off is noise: the screen is exactly where the
        person just asked it to be.
        """
        if self.state is MediaPlayerState.IDLE:
            return
        await self.coordinator.async_control("stop")

    async def async_media_next_track(self) -> None:
        await self.coordinator.async_next()

    async def async_media_seek(self, position: float) -> None:
        """The serve seeks by a signed offset, so the target is turned into one."""
        current = self._snapshot.get("position")
        if current is None:
            raise HomeAssistantError("torrcast does not know the current position to seek from")
        await self.coordinator.async_control("seekby", round(position - float(current), 3))

    async def async_media_previous_track(self) -> None:
        """Restarts the show now on the screen from its own beginning, not a track before it.

        Home Assistant draws `PREVIOUS_TRACK` as the left arrow next to the already-live
        right arrow of `async_media_next_track` (`POST /api/next`, a different release
        file), and the owner asked for that left arrow to mean "play this same episode or
        movie from zero" - no change of release, file, or track, no reconnect to the
        receiver. The bridge has no route of its own for that: `async_media_seek` already
        turns any target position into the signed `seekby` offset the serve takes, so
        zero is just the target `0.0`, and a person without a known position gets the
        same readable refusal a seek to any other point would.
        """
        await self.async_media_seek(0.0)

    async def async_set_volume_level(self, volume: float) -> None:
        await self.coordinator.async_control("volume", round(volume, 3))

    async def async_volume_up(self) -> None:
        await self._async_volume_by(VOLUME_STEP)

    async def async_volume_down(self) -> None:
        await self._async_volume_by(-VOLUME_STEP)

    async def _async_volume_by(self, step: float) -> None:
        """A step needs a level to start from; without one nothing is invented."""
        current = self.volume_level
        if current is None:
            raise HomeAssistantError("torrcast does not know the current volume of the receiver")
        await self.async_set_volume_level(min(1.0, max(0.0, current + step)))
