"""One media player entity: the TV as torrcast sees it."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VOLUME_STEP
from .coordinator import TorrcastConfigEntry, TorrcastCoordinator

_LOGGER = logging.getLogger(__name__)

#: The five words of the contract and what Home Assistant calls the same thing.
STATES: dict[str, MediaPlayerState] = {
    "idle": MediaPlayerState.IDLE,
    "starting": MediaPlayerState.BUFFERING,
    "playing": MediaPlayerState.PLAYING,
    "paused": MediaPlayerState.PAUSED,
    "torn": MediaPlayerState.IDLE,
}


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
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.SEEK
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
    )

    def __init__(self, coordinator: TorrcastCoordinator, entry: TorrcastConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entry.unique_id or entry.entry_id
        snapshot = coordinator.data or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            manufacturer="torrcast",
            name=snapshot.get("tv") or "torrcast",
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
        """The content type is not looked at: the identifier is the search query itself."""
        _LOGGER.debug("play %s (type %s, extras %s)", media_id, media_type, kwargs)
        await self.coordinator.async_play(media_id)

    async def async_media_play(self) -> None:
        await self.coordinator.async_control("toggle")

    async def async_media_pause(self) -> None:
        await self.coordinator.async_control("toggle")

    async def async_media_play_pause(self) -> None:
        await self.coordinator.async_control("toggle")

    async def async_media_stop(self) -> None:
        await self.coordinator.async_control("stop")

    async def async_media_next_track(self) -> None:
        await self.coordinator.async_next()

    async def async_media_seek(self, position: float) -> None:
        """The serve seeks by a signed offset, so the target is turned into one."""
        current = self._snapshot.get("position")
        if current is None:
            raise HomeAssistantError("torrcast does not know the current position to seek from")
        await self.coordinator.async_control("seekby", round(position - float(current), 3))

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
