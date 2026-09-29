"""Байты постера с запасным адресом: зависший хост одного источника не оставляет плитку пустой.

🔴 Гонка источников отдаёт плитке адреса ОДНОГО источника - того, кто ответил первым
(:class:`hass.both_posters.BothPosters`). Когда хост его картинок замолкает целиком
(у IMDb это обрыв чтения на каждом холодном файле), плитка теряла все адреса разом,
а повтор снова приходил в ту же гонку и снова получал те же адреса: «Начало» 25 раз
подряд оставалось без единой обложки в чистой сети, хотя у Википедии обложки были.

Поэтому плитка, не получившая байт ни по одному адресу, качает НОВЫЕ адреса из ответа
проигравшего источника той же гонки (:meth:`hass.poster_race.PosterRace.spare`). Этот
ответ уже в памяти или ещё едет по запросу, оплаченному гонкой: запас стоит ожидания и
загрузки файла, но ни одного нового запроса к API источников. Плитка, у которой гонки
не было (спокойный путь), запаса не получает.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.adapters.wiki.poster_bodies import PosterBodies
from torrcast.domain.facts.ask import Ask


def spare_bodies(
    pictures: PosterBodies,
    spare: Callable[[Ask], list[str]],
    wanted: dict[Ask, list[str]],
    timeout: float,
) -> dict[Ask, bytes]:
    """Байты по названным адресам; оставшимся без байт - адреса, которых они ещё не пробовали.

    ``spare`` отдаёт уже полученные адреса картины и в сеть сам не ходит.
    """
    got = pictures.bodies(wanted, timeout)
    fresh: dict[Ask, list[str]] = {}
    for ask, tried in wanted.items():
        if tried and ask not in got:
            new = [address for address in dict.fromkeys(spare(ask)) if address not in tried]
            if new:
                fresh[ask] = new
    if fresh:
        got.update(pictures.bodies(fresh, timeout))
    return got
