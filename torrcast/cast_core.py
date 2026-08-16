"""Договор приёмника: что показ о нём знает и чему приёмник должен доверять.

Отдельно от реализаций нарочно. Приёмников два - живой Chromecast
(:mod:`torrcast.cast`) и сухая заглушка (:mod:`torrcast.cast_mock`), - и обоим нужно одно
и то же: класс позиции, протокол, по которому их зовёт показ, и разбор доверенного
корня. Держать это у одной из реализаций значило бы, что вторая импортирует первую
ради трёх объявлений, а фасад :mod:`torrcast.cast` - обе, и импорт замкнулся бы в кольцо.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = [
    "Position",
    "Receiver",
    "trust_anchor",
]


@dataclass(frozen=True, slots=True)
class Position:
    pos: float
    dur: float
    playing: bool = False
    #: Состояние приёмника как есть (``PLAYING``/``BUFFERING``/``PAUSED``/``IDLE``).
    #: Показу нужно отличать паузу на пульте от конца фильма: на паузе упаковка гасится,
    #: но показ жив и продолжится с того же места.
    state: str = ""

    @property
    def ratio(self) -> float:
        return self.pos / self.dur if self.dur > 0 else 0.0


@runtime_checkable
class Receiver(Protocol):
    """Что нам нужно от приёмника — и ничего сверх того."""

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        """Начать воспроизведение HLS-манифеста с секунды ``at``."""

    def stop(self, quit_app: bool = False) -> None:
        """Снять каст; ``quit_app`` — ещё и закрыть приложение приёмника.

        ``quit_app=False`` — показ передают дальше (стык серий): приложение остаётся
        открытым, следующая серия грузится в него же.
        """

    def position(self, front: float = 0.0) -> Position:
        """Текущая позиция и длительность; ``front`` — докуда упаковано."""


def trust_anchor(cert: str) -> str:
    """Чему приёмник должен доверять, проверяя нашу раздачу.

    Серт выпущен настоящим CA (LE) — доверяем **системному хранилищу**: ровно
    так его проверит ТВ, и только такая проверка закрывает требование Chromecast к
    доверенному HTTPS. Серт self-signed (дефолт `install.sh` до доставки LE) — доверяем
    ему самому: иначе проверять нечем.

    Различаем по файлу: OpenSSL берёт в доверенные только CA-сертификаты, поэтому у
    self-signed остаётся он сам (subject == issuer), а у цепочки LE — промежуточный
    (subject != issuer), листа в списке нет вовсе.
    """
    import ssl

    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=cert)
        anchors = context.get_ca_certs()
    except (OSError, ssl.SSLError):
        return cert  # нечитаемый серт - пусть падает там, где это видно
    if len(anchors) == 1 and anchors[0].get("subject") == anchors[0].get("issuer"):
        return cert
    return ""
