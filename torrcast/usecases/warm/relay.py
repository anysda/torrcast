"""Перекладывает точечные куски, оставшиеся от прежнего способа выкладки."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from torrcast.usecases.warm._vault_disk import _lay, _spot_marks


class _Vault(Protocol):
    @property
    def dir(self) -> Path: ...

    @property
    def lay(self) -> str: ...

    def reject(self, slot: int) -> None: ...

    def touch(self) -> None: ...


def relay(vault: _Vault) -> tuple[int, ...]:
    """Убрать куски, положенные ПРЕЖНИМ способом выкладки; вернуть их места.

    Способ выкладки в ключ каталога не входит и входить не должен
    (:func:`torrcast.usecases.warm.warm_key.warm_key`): ключ называет содержимое куска, а на
    детерминированной сетке стоит переиспользование прошлых заходов. Из-за этого каталог,
    прогретый прежним способом, находится по тому же ключу, метки ``v{N}.rec`` считают его
    точечные куски сделанными, и починка выкладки до них не доезжает - старые куски лежат
    под теми же именами и уезжают зрителю.

    Перекладываются ровно помеченные места, а не весь каталог: копию точечная работа не
    трогала, и сброс каталога целиком стоил бы прогрева заново. Кусок стирается вместе с
    меткой - иначе он числился бы сделанным (:func:`torrcast.usecases.warm.missing._missing`,
    :func:`torrcast.usecases.warm._warm_count._spots_left`) и остался бы лежать как есть.

    🔴 Стирается именно ФАЙЛ, а не одна метка. Точечный перекод кладётся поверх копии
    этого же места и берёт её звук (:func:`torrcast.adapters.stream_pack.spot_out.spot_out`);
    под старым куском копии больше нет, и перекод поверх него взял бы звук у него же -
    то есть у той самой рваной сетки, ради которой всё и затевалось. Копию возвращает
    обычный заход прогрева, одним прогоном и одним непрерывным звуком.

    Зовётся ОДИН раз, когда каталог заводят
    (:func:`torrcast.usecases.playback._warmer._warmer`), а не при выдаче: прогретое читается
    показом первым, и проверка на этом пути стоила бы чтения куска на каждый запрос.
    """
    if _lay(vault.dir) == vault.lay:
        return ()
    gone = tuple(_spot_marks(vault.dir))
    for slot in gone:
        vault.reject(slot)
    if gone:
        vault.touch()
    return gone
