"""Два источника картинок подряд: Википедия отвечает первой, IMDb добирает молчащих.

Порядок тут не про вкус, а про доверие. Обложка в статье Википедии - это обложка ИМЕННО
той картины, про которую статья, со сверенным годом выхода; подсказчик IMDb ранжирует по
популярности и тёзку от тёзки отличает только годом. Поэтому второй спрашивается ровно о
тех картинах, о которых первый промолчал, и ни одной картинки первого не подменяет.

Байты у обоих одни и те же: приговор каждого - это готовый адрес файла, и качаются они
общим шагом (:class:`~torrcast.adapters.wiki.poster_bodies.PosterBodies`). Разделять их
по источнику было бы вымыслом: обоим адресам одинаково нужен один GET.
"""

from __future__ import annotations

from collections.abc import Sequence

from hass.poster_source import PosterSource
from torrcast.adapters.wiki.poster_bodies import PosterBodies
from torrcast.domain.facts.ask import Ask
from torrcast.ports.bytes_client import BytesClient


class BothPosters:
    """Приговор первого источника, а на промолчавших - приговор второго."""

    def __init__(self, first: PosterSource, second: PosterSource, files: BytesClient) -> None:
        self.first = first
        self.second = second
        self.pictures = PosterBodies(files)

    def poster(self, ask: Ask, timeout: float) -> bytes | None:
        """Байты постера одной картины; постера у неё нет ни там, ни там - ``None``.

        Дверь карточки играющего идёт теми же двумя источниками, что и список обзора, и
        это обязательно: полка у них общая, и разойдись правила - человек увидел бы в
        списке одну картинку, а на экране другую.
        """
        return self.bodies(self.wanted([ask], timeout), timeout).get(ask)

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        """Адреса постеров: чьи назвал первый источник, остальные - у второго.

        🔴 Тем, о ком первый уже сказал, второго не спрашивают вовсе - и это ровно одно
        место, а не два: сведи ответы «первый важнее» ещё и на слиянии, обе страховки
        стали бы зелёными поодиночке, и ни одна проба не показала бы, работает ли хоть
        одна из них.

        🔴 Обрыв второго не стирает ответ первого. Второй тут добирает, а не решает, и
        его молчание обязано выглядеть как «этим картинам картинки не нашлось» - иначе
        одна сетевая ошибка уносила бы и те картинки, которые уже были найдены.
        """
        found = self.first.wanted(asks, timeout)
        left = [ask for ask in asks if not found.get(ask)]
        if not left:
            return found
        try:
            more = self.second.wanted(left, timeout)
        except Exception:
            more = {}
        answers = {**found, **{ask: more.get(ask, []) for ask in left}}
        return {ask: answers.get(ask) or [] for ask in asks}

    def bodies(self, wanted: dict[Ask, list[str]], timeout: float) -> dict[Ask, bytes]:
        """Байты постеров по названным адресам; чей источник их назвал - уже неважно."""
        return self.pictures.bodies(wanted, timeout)
