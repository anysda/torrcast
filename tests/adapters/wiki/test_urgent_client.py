"""Checks the urgent view of the Wikimedia client used by the visible list's posters."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.wiki.http_json_client import HttpJsonClient
from torrcast.adapters.wiki.urgent_client import UrgentClient


def test_the_visible_list_asks_the_real_client_urgently() -> None:
    """Both JSON and image requests of the view carry ``urgent``."""
    client = HttpJsonClient("torrcast/test")
    said: list[tuple[str, dict[str, Any]]] = []

    def get(*_args: Any, **kwargs: Any) -> Any:
        said.append(("get", kwargs))
        return {}

    def fetch(*_args: Any, **kwargs: Any) -> bytes:
        said.append(("fetch", kwargs))
        return b"x"

    client.get = get  # type: ignore[method-assign]
    client.fetch = fetch  # type: ignore[method-assign]
    view = UrgentClient(client)
    assert view.get("ru.wikipedia.org", "/w/api.php", {}, {}, 1.0) == {}
    assert view.fetch("https://upload.wikimedia.org/a.jpg", 1.0) == b"x"
    assert [kwargs.get("urgent") for _, kwargs in said] == [True, True]


def test_a_fake_client_passes_through_the_view() -> None:
    """A test double without urgency still answers through the view."""

    class _Fake:
        def get(self, *args: Any, foreground: bool = False) -> Any:
            return {"foreground": foreground}

        def fetch(self, address: str, timeout: float) -> bytes:
            return address.encode()

        def warm(self, host: str) -> None:
            return None

    view = UrgentClient(_Fake())
    assert view.get("h", "/", {}, {}, 1.0, foreground=True) == {"foreground": True}
    assert view.fetch("a", 1.0) == b"a"
