"""Слоты каталога раздач и справки о картинах.

Ставит их композиционный корень (:func:`torrcast.runtime.wire.wire`), спрашивают все
круги добора."""

from __future__ import annotations

from torrcast.ports.passport_source import PassportSource
from torrcast.ports.torrent_catalogue import TorrentCatalogue

#: Каталог раздач и справка о картинах - единственное, что у добора снаружи. Ставит их
#: корень: за первым стоит адаптер индексеров, за второй - паспорт справки, и оба он же
#: раздаёт поиску.
#:
#: ⚠️ Имена тут длиннее очевидных нарочно. Плоский namespace прежнего монолита
#: (:mod:`torrcast.cli`) вписывает в КАЖДУЮ свою часть globals всех остальных, и короткое
#: ``_passport`` тут же затирается одноимённой функцией отбора
#: (:func:`torrcast.usecases.choice._passport`) - справка молча превращается в чужую
#: функцию, и добор падает на первом же вопросе о годе.
_catalogue: TorrentCatalogue
_passport_source: PassportSource


def configure(catalogue: TorrentCatalogue, passport: PassportSource) -> None:
    """Передать сценарию каталог раздач и справку о картинах."""
    global _catalogue, _passport_source
    _catalogue, _passport_source = catalogue, passport


def _catalogue_port() -> TorrentCatalogue:
    """Каталог раздач, поставленный :func:`configure`."""
    return _catalogue


def _passport_port() -> PassportSource:
    """Справка о картинах, поставленная :func:`configure`."""
    return _passport_source
