"""Single-owner poster verdict used by final searches, previews, and redress."""

from __future__ import annotations

import threading
from collections.abc import Callable

from torrcast.domain.json_value import JsonValue
from torrcast.domain.torrcast_error import TorrcastError

_Offer = Callable[[list[JsonValue]], list[JsonValue]]


class SearchPosterVerdict:
    """Poster-verdict behavior for :class:`hass.search_job.SearchJob`."""

    posters: dict[str, JsonValue]
    _verdict: threading.Lock

    @property
    def judging(self) -> bool:
        """Whether one owner currently holds the poster verdict lock."""
        return self._verdict.locked()

    def _claim_verdict(self) -> bool:
        """Become the sole poster judge without making an HTTP poll wait."""
        return self._verdict.acquire(blocking=False)

    def _finish_verdict(self) -> None:
        """Release a verdict claimed by this execution path."""
        self._verdict.release()

    def dress(self, hits: list[JsonValue], offer: _Offer) -> list[JsonValue]:
        """Return known covers now and start exactly one verdict for the missing ones."""
        if any(_key(hit) not in self.posters for hit in hits) and self._claim_verdict():
            worker = threading.Thread(target=self._judge_alone, args=(hits, offer), daemon=True)
            try:
                worker.start()
            except BaseException:
                self._finish_verdict()
                raise
        return [
            {**hit, "poster": self.posters[_key(hit)]}
            if isinstance(hit, dict) and self.posters.get(_key(hit)) is not None
            else hit
            for hit in hits
        ]

    def _judge_alone(self, hits: list[JsonValue], offer: _Offer) -> None:
        try:
            self._judge(hits, offer)
        finally:
            self._finish_verdict()

    def _judge(self, hits: list[JsonValue], offer: _Offer) -> None:
        try:
            judged = offer(hits)
        except (TorrcastError, OSError):
            judged = []
        for before, after in zip(hits, judged, strict=False):
            # A silent retry does not take away a poster already named by an earlier verdict.
            if isinstance(after, dict) and (
                after.get("poster") or _key(before) not in self.posters
            ):
                self.posters[_key(before)] = after.get("poster")


def _key(hit: JsonValue) -> str:
    return str(hit.get("key", "")) if isinstance(hit, dict) else ""


__all__ = ["SearchPosterVerdict"]
