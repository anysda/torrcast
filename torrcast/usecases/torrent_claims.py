"""Кто в этом процессе держит раздачу TorrServer: снос чужого держателя не трогает.

``add`` в TorrServer идемпотентен, и одну раздачу держат сразу несколько частей одного
процесса: карточка страницы читает дорожки той раздачи, которую показ в эту же секунду
отбирает, разбор серий спрашивает раздачу играющего сезона. Снос по уборке одного из них
выдёргивал раздачу из-под другого (стенд 14-09-2026: «Тачки» с карточки упали на 404,
TorrServer закрыл раздачу по сносу прогрева карточки).

Отметка показа в состоянии (:func:`torrcast.usecases.torrents._held_by_show`) этого не
видит: её ставит юнит, а отбор идёт до него. Поэтому держатели внутри процесса
отмечаются здесь, а снос спрашивает обе отметки.
"""

from __future__ import annotations

import contextlib
import threading
import weakref
from collections.abc import Callable, Iterator
from typing import Final

from torrcast.domain.magnet_hash import magnet_hash
from torrcast.domain.torrent_hash import _torrent_hash


class TorrentClaims:
    """Держатели раздач по хэшу: каждый ставит свою отметку и снимает только её."""

    def __init__(self) -> None:
        #: Повторный вход нужен сносу: его проверка «ничья ли» сама спрашивает :meth:`claimed`.
        self._lock = threading.RLock()
        #: Держатель - сам живой объект, а не запись о нём: стенд, брошенный на исключении
        #: без уборки, уходит сборщику мусора вместе со своими отметками.
        self._owners: dict[str, list[weakref.ref[object]]] = {}
        #: Кто-то ждал замка, пока шёл последний снос (:meth:`waited`).
        self._waited = False
        #: Сколько держателей стоят на замке прямо сейчас: метку снос сбрасывает, а очередь
        #: за ним видна по счёту. Счёт меняется под своим замком, иначе гонка ``+=`` теряла бы
        #: приращение, и уборка уступала бы вечно.
        self._waiting = 0
        self._counting = threading.Lock()

    @contextlib.contextmanager
    def _held(self) -> Iterator[None]:
        """Замок отметок; не взялся с ходу - держатель ждёт, и уборка ему уступит."""
        if not self._lock.acquire(blocking=False):
            with self._counting:
                self._waiting += 1
            try:
                self._waited = True
                self._lock.acquire()
            finally:
                with self._counting:
                    self._waiting -= 1
        try:
            yield
        finally:
            self._lock.release()

    def claim(self, torrent_hash: str, owner: object) -> None:
        """Отметить, что ``owner`` держит раздачу; пустой хэш не отмечается."""
        if not torrent_hash:
            return
        with self._held():
            owners = self._alive(torrent_hash, owner)
            self._owners[torrent_hash] = [*owners, weakref.ref(owner)]

    def unclaim(self, torrent_hash: str, owner: object) -> bool:
        """Снять отметку ``owner``; правда - других держателей в процессе не осталось."""
        with self._held():
            owners = self._alive(torrent_hash, owner)
            if owners:
                self._owners[torrent_hash] = owners
                return False
            self._owners.pop(torrent_hash, None)
            return True

    def claimed(self, torrent_hash: str) -> bool:
        """Держит ли раздачу кто-нибудь в этом процессе."""
        with self._held():
            return bool(self._alive(torrent_hash, None))

    def _alive(self, torrent_hash: str, but: object) -> list[weakref.ref[object]]:
        """Живые держатели раздачи, кроме ``but``; ушедшие сборщику отметок не держат."""
        refs = self._owners.get(torrent_hash, [])
        return [ref for ref in refs if (held := ref()) is not None and held is not but]

    def adding(self, magnet: str, owner: object, add: Callable[[str], str]) -> str:
        """Добавить раздачу, отметив её держателя ДО ``add``, а не после.

        ``add`` в TorrServer идемпотентен: раздача, которую прямо сейчас убирает другой
        держатель, отвечает на ``add`` своим хэшем - и снос, успевший между ответом и
        отметкой, выдёргивает её из-под нового держателя. Отметка по хэшу магнита стоит
        раньше, поэтому такой снос её видит; base32-магнит отмечается тем hex, которым
        раздачу называет служба. Не вышло - отметка снимается.
        """
        early = _torrent_hash(magnet) or magnet_hash(magnet)
        self.claim(early, owner)
        torrent_hash = ""
        try:
            torrent_hash = add(magnet)
            self.claim(torrent_hash, owner)
        finally:
            if early != torrent_hash:
                self.unclaim(early, owner)
        return torrent_hash

    def dropping(self, torrent_hash: str, drop: Callable[[str], bool]) -> bool:
        """Проверить и снести раздачу под замком отметок: :meth:`adding` ждёт конца сноса.

        Проверка «ничья ли» и снос врозь - окно гонки: держатель отмечал раздачу и заводил её
        между ними, а снос выдёргивал её из-под него. Под замком держатель либо успел, и
        проверка его видит, либо заводит раздачу после сноса заново.
        """
        with self._lock:
            self._waited = False
            return drop(torrent_hash)

    def waited(self) -> bool:
        """Ждал ли кто-нибудь замка, пока шёл последний :meth:`dropping`.

        Замок не честный: уборка, сносящая раздачи подряд, перехватывает его между сносами,
        и заводящий раздачу ждал бы все её сетевые ``rem``, а не один. Уборка спрашивает
        это после каждого сноса и уступает. Держатель, вставший в очередь ещё до сноса,
        виден по счёту: метку снос стёр, а ждать он продолжает.
        """
        return self._waited or self._waiting > 0

    @contextlib.contextmanager
    def kept(self, torrent_hash: str, owner: object) -> Iterator[None]:
        """Держать раздачу, пока идёт блок, и отпустить на любом выходе из него.

        Так отбор держит взятую раздачу до подъёма показа: дальше её держит отметка юнита
        в состоянии, а стенда отбора уже нет.
        """
        self.claim(torrent_hash, owner)
        try:
            yield
        finally:
            self.unclaim(torrent_hash, owner)


#: Держатели раздач этого процесса: страница и показ живут в одном мосту.
CLAIMS: Final = TorrentClaims()
