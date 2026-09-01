"""Английские надписи кластера обновления."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера обновления."""
    return {
        "upgrade.needs_root": "root is required: run cast --upgrade as root",
        "upgrade.elevating": "not root - restarting through sudo",
        "upgrade.no_loader": (
            "this copy was installed before cast --upgrade existed; update it once with"
            " curl -fsSL https://torrcast.anysda.space | sh"
        ),
        "upgrade.show_is_on": (
            "“{what}” is playing right now, and the update restarts the units that carry"
            " it - stop the show first: cast stop"
        ),
        "upgrade.show_is_on_unnamed": (
            "a show is running right now, and the update restarts the units that carry"
            " it - stop the show first: cast stop"
        ),
        "upgrade.failed": "the update did not go through - torrcast {version} is still installed",
    }
