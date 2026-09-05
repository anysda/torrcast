"""The buttons of the card, turned into the commands the serve already takes."""

from __future__ import annotations

from homeassistant.components.media_player import MediaPlayerEntity, MediaPlayerState
from homeassistant.exceptions import HomeAssistantError

from .const import VOLUME_STEP


class Remote(MediaPlayerEntity):
    """What every button of the card sends; the entity itself is assembled in `player`."""

    async def async_media_play(self) -> None:
        """On an empty screen this is the card's only button; everywhere else, `toggle`.

        An empty screen has nothing to pause or resume by that name, and the owner asked
        for the one button left there to carry on with the last thing watched from the
        second it was left at - what `cast` with no words after it does in the terminal.
        Nothing is decided here: the serve is asked for that bare `cast` as such
        (:meth:`Coordinator.async_resume`), and which picture and which second those are
        stays the product's own single answer.
        """
        if self.state is MediaPlayerState.IDLE:
            await self.coordinator.async_resume()
            return
        await self.coordinator.async_control("toggle")

    async def async_media_pause(self) -> None:
        await self.coordinator.async_control("toggle")

    async def async_media_play_pause(self) -> None:
        """A script or a voice command can reach this instead of `async_media_play`.

        The card itself only ever sends `media_play` from an empty screen (there is no
        pause button there to combine with), but a voice assistant or an automation
        knows the single `media_play_pause` service, and `toggle` on an empty screen is
        the refusal the owner already asked to stop showing (`Remote.async_media_play`).
        The idle branch is repeated rather than shared, because sharing it would mean
        this button also deciding what a bare `cast` plays - a call `async_media_play`
        does not make either.
        """
        if self.state is MediaPlayerState.IDLE:
            await self.coordinator.async_resume()
            return
        await self.coordinator.async_control("toggle")

    async def async_media_stop(self) -> None:
        await self.coordinator.async_control("stop")

    async def async_turn_off(self) -> None:
        """The power button of the card: puts the show out, live only.

        Off means the show, not the mains: the product has no way to unplug a television
        and does not pretend to. It is the same `stop` the console and the bot send, so
        the button opens no new road outwards. An empty screen no longer claims this
        button at all (`Player.supported_features`): reading the last show back up moved
        to the one button that stays, `async_media_play`, and there is nothing left here
        to decide between the two.
        """
        await self.coordinator.async_control("stop")

    async def async_media_next_track(self) -> None:
        await self.coordinator.async_next()

    async def async_media_seek(self, position: float) -> None:
        """The serve seeks by a signed offset, so the target is turned into one."""
        current = (self.coordinator.data or {}).get("position")
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
