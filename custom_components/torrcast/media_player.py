"""The media player platform of the integration: one serve is one TV, so one entity."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import TorrcastConfigEntry
from .player import Player

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    # The platform contract names `hass` first even where the body has no use for it;
    # dropping the parameter would break the call, not tidy it up.
    hass: HomeAssistant,  # noqa: ARG001
    entry: TorrcastConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """One serve is one TV, so the platform adds exactly one entity."""
    _LOGGER.debug("adding the player of %s", entry.runtime_data.base_url)
    async_add_entities([Player(entry.runtime_data, entry)])
