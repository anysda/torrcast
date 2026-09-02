"""Одна строка зрителю о том, что телевизор уже занят нашим показом.
Зовёт её команда показа перед меню картин (:func:`torrcast.usecases.cast_command._cmd_play`).
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.tongue import EN, tongue
from torrcast.domain.entry import Entry
from torrcast.domain.facts.origin import Origin

__all__ = ["Entry", "_say_showing"]

from torrcast.usecases.choice._named import _CYRILLIC
from torrcast.usecases.rank._hms import _hms


def _say_showing(
    live: tuple[str, Entry] | None,
    origin: Callable[[str, bool | None], Origin | None] | None = None,
) -> None:
    """Сказать зрителю, что телевизор уже занят НАШИМ показом, и что будет дальше.

    Одна строка человеческими словами и без единого слова из машинного словаря: зритель
    вправе знать, что он сейчас прервёт, ещё до того как ответит на вопрос меню. Раньше
    вторая команда вела себя как первая - молча качала свои раздачи рядом с играющим
    фильмом и обрывала его в момент выбора; ни того, ни другого на экране видно не было.

    Занятость берётся из нашего состояния
    (:meth:`torrcast.adapters.filesystem.state.state.State.showing`) и только оттуда:
    спросить сам приёмник значит подключиться к нему вторым сендером и погасить
    показ, который мы как раз и бережём
    (:class:`torrcast.adapters.chromecast.cast.chromecast_receiver.ChromecastReceiver`).

    Имя картины - с языковой стороны продукта (:func:`_showing_name`), а кавычки вокруг
    него - из каталога фразы, и потому обоих наборов по одному на каждый язык.
    """
    if live is None:
        return
    entry = live[1]
    what = phrase("choice.quoted", it=_showing_name(entry, origin)) + (
        f", {entry.label}" if entry.label else ""
    )
    where = f" {phrase('showing.at', pos=_hms(entry.pos))}" if entry.pos > 0 else ""
    print(phrase("showing.busy", what=what, where=where), flush=True)


def _showing_name(entry: Entry, origin: Callable[[str, bool | None], Origin | None] | None) -> str:
    """Имя играющей картины с языковой стороны продукта.

    Под EN картину зовёт её оригинальное имя из самой записи (:attr:`Entry.original`).
    Записей прежних версий оно не знает - для них читается КЭШ справки
    (:meth:`torrcast.adapters.wiki.facts_file_cache.FactsFileCache.read`): первый показ
    этой картины уже спрашивал её паспорт и записал ответ на диск. Порядок рядов - как у
    памяти дорожек (:func:`torrcast.runtime.native_picture.native_picture`): сначала ряд
    с типом записи, затем ряд без типа.

    Кэш молчит или английского имени в нём нет (отечественная картина) - показывается
    записанное имя как есть. Молчать о том, что играет, нельзя, а придуманного имени
    (транслита) у картины нет: честная строка с русским именем лучше выдуманной.
    """
    if tongue() != EN:
        return entry.title
    if entry.original:
        return entry.original
    if origin is None:
        return entry.title
    about = origin(entry.title, entry.kind == "tv") or origin(entry.title, None)
    if about and about.title and not _CYRILLIC.search(about.title):
        return about.title
    return entry.title
