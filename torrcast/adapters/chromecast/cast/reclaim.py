"""Release a previous sender's application before loading our stream again."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from torrcast.adapters.chromecast.cast.while_connecting import _while_connecting
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.why import why

if TYPE_CHECKING:
    from torrcast.adapters.chromecast.cast.receiver_talk import _Talk


def reclaim(rcv: _Talk, url: str) -> None:
    """A receiver outlives its sender, including a sender killed while paused.

    Recover on the next explicit play, not on service startup: connecting wakes the
    TV and could interfere with a live CLI sender. The URL supplied to play is the
    manifest built from this installation's hls_base, including any configured
    prefix. An app ID alone cannot distinguish another sender's media receiver.

    Read a completed status reply before deciding ownership; device.wait() only
    waits for the application status, not for its media. Unknown content is never
    evidence of ownership. Keep the same sender's app between episodes.
    """
    if rcv._session:
        return
    device = rcv._device()
    if device.status.app_id != rcv.MEDIA_APP:
        return
    from pychromecast.response_handler import WaitResponse

    session = device.status.session_id
    reply = WaitResponse(10, "previous cast status")
    try:
        _while_connecting(
            rcv,
            "GET_STATUS",
            lambda: device.media_controller.update_status(callback_function=reply.callback),
        )
        reply.wait_response()
    except Exception as exc:
        # Ownership was not established. A failed load's cleanup must not mistake
        # the unclaimed app for ours just because no URL has been loaded yet.
        with contextlib.suppress(Exception):
            device.disconnect()
        rcv._cast = None
        raise InfraError(
            phrase("chromecast_talk.tv_rejected_cast", address=rcv.address, reason=why(exc))
        ) from exc
    if (
        device.status.app_id == rcv.MEDIA_APP
        and device.status.session_id == session
        and device.media_controller.status.content_id == url
    ):
        rcv._restart_app()
