"""Оба пути внутрь: объявление по mDNS и адрес, введённый руками."""

from __future__ import annotations

from ipaddress import ip_address
from typing import Any

import pytest
from homeassistant.config_entries import (  # type: ignore[import-not-found]
    SOURCE_USER,
    SOURCE_ZEROCONF,
)
from homeassistant.core import HomeAssistant  # type: ignore[import-not-found]
from homeassistant.data_entry_flow import FlowResultType  # type: ignore[import-not-found]
from homeassistant.helpers.service_info.zeroconf import (  # type: ignore[import-not-found]
    ZeroconfServiceInfo,
)

from tests.hass_integration.conftest import BASE, DOMAIN, HOST, PORT, mount, snapshot

ANNOUNCED = ZeroconfServiceInfo(
    ip_address=ip_address(HOST),
    ip_addresses=[ip_address(HOST)],
    port=PORT,
    hostname="torrcast.local.",
    type="_torrcast._tcp.local.",
    name="torrcast._torrcast._tcp.local.",
    properties={"version": "0.99.99", "tv": "TV"},
)


@pytest.fixture(autouse=True)
def _custom_integrations(request: Any) -> None:
    """Даёт Home Assistant увидеть `custom_components/torrcast` в дереве репозитория."""
    request.getfixturevalue("enable_custom_integrations")
    mount()


async def test_zeroconf_flow_writes_the_entry(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """Объявленный по mDNS серве спрашивают о состоянии и заводят после подтверждения."""
    aioclient_mock.get(f"{BASE}/api/state", json=snapshot())
    found = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=ANNOUNCED
    )
    assert found["type"] is FlowResultType.FORM
    assert found["step_id"] == "zeroconf_confirm"

    written = await hass.config_entries.flow.async_configure(found["flow_id"], {})
    assert written["type"] is FlowResultType.CREATE_ENTRY
    assert written["title"] == "torrcast (TV)"
    assert written["data"] == {"host": HOST, "port": PORT}


async def test_manual_flow_writes_the_entry(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """Адрес руками - запасной путь для сети, которая ест multicast."""
    aioclient_mock.get(f"{BASE}/api/state", json=snapshot())
    asked = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert asked["step_id"] == "user"

    written = await hass.config_entries.flow.async_configure(
        asked["flow_id"], {"host": HOST, "port": PORT}
    )
    assert written["type"] is FlowResultType.CREATE_ENTRY
    assert written["data"] == {"host": HOST, "port": PORT}
    assert written["result"].unique_id == f"{HOST}:{PORT}"


async def test_silent_serve_is_not_written(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """Молчащий адрес не заводится: форма возвращается с названной причиной."""
    aioclient_mock.get(f"{BASE}/api/state", exc=TimeoutError())
    asked = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    refused = await hass.config_entries.flow.async_configure(
        asked["flow_id"], {"host": HOST, "port": PORT}
    )
    assert refused["type"] is FlowResultType.FORM
    assert refused["errors"] == {"base": "cannot_connect"}
