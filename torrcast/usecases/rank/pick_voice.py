"""Какую дорожку играем и что после этого лежит в памяти картины; зовёт запуск показа."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.rank_settings import VOICE_MENU
from torrcast.domain.studio import Studio
from torrcast.domain.track_studio import track_studio
from torrcast.usecases.rank.configure import _console_port
from torrcast.usecases.rank.spoken_voice import spoken_voice
from torrcast.usecases.rank.voices_table import voices_table


class _Voiced(Protocol):
    """Разобранная строка запуска в объёме, который нужен выбору дорожки: ``--voice N``.

    Полный :class:`torrcast.domain.args.Args` сюда не приходит: разбор аргументов стоит слоем
    выше сценариев, а выбору дорожки от него нужна одна ручка.
    """

    voice: int | str | None


def pick_voice(
    media: Media,
    args: _Voiced,
    remembered: str = "",
    native: bool = False,
    studios: Sequence[Studio] = (),
) -> tuple[int, str]:
    """Какую дорожку играем и что после этого лежит в памяти картины.

    **На счастливом пути вопроса про озвучку нет.** Дорожка выбирается сама
    (:meth:`Media.default_track`), и её подпись печатается в строке запуска —
    молчаливых подмен не бывает.

    Спросить можно только явно: ``--voice N`` берёт дорожку N, ``--voice ИМЯ`` ищет
    подпись или студию, ``--voice`` без значения показывает меню. Слово сравнивается
    целиком без учёта регистра и пробелов, но не как подстрока: ``MVO`` не совпадает с
    ``MVO (LostFilm)``. Явный выбор, и только он, пишется в память картины
    (:attr:`torrcast.domain.entry.Entry.voice`). Автовыбор память не трогает: иначе первый же
    запуск с другим релизом переписал бы то, что пользователь выбрал руками.

    ``native`` — картина снята по-русски: тогда сама собой выбирается её собственная
    дорожка, а не переозвучка поверх неё (:func:`~torrcast.domain.voice_order.voice_order`).

    Возвращает пару «номер дорожки в этом релизе, память картины».
    """
    if not media.tracks:
        raise InfraError(phrase("rank.no_audio_tracks"))
    if args.voice is not None:
        if args.voice == VOICE_MENU:
            index = _ask_voice(media, native, studios)
            return index, media.tracks[index].label
        if isinstance(args.voice, str):
            index, name = _voice_name(media, args.voice, studios)
            return index, name
        index = _voice_number(media, args.voice)
        return index, media.tracks[index].label
    if remembered:
        found = media.find_voice(remembered)
        if found is None:
            found = _named_index(media, remembered, studios)
        if found is not None:
            return found, remembered
        # Память живёт на картину, а релиз временный: озвучки в нём нет - говорим и
        # играем обычную, но выбор пользователя не забываем (:attr:`Entry.voice`).
        _console_port().write(phrase("rank.voice_kept_usual", name=spoken_voice(remembered)))
    return media.default_track(native), remembered


def _voice_number(media: Media, number: int) -> int:
    """Номер дорожки от человека → индекс; чужого номера нет — честная строка."""
    if not 1 <= number <= len(media.tracks):
        raise NotFoundError(
            phrase("rank.voice_number_missing", total=len(media.tracks), number=number)
        )
    return number - 1


def _voice_name(media: Media, name: str, studios: Sequence[Studio]) -> tuple[int, str]:
    """Точное имя подписи или студии; регистр и пробелы значения не имеют."""
    found = _named_index(media, name, studios)
    if found is not None:
        studio = track_studio(media, found, studios)
        return found, studio.name if studio is not None else media.tracks[found].label
    raise NotFoundError(phrase("rank.voice_name_missing", name=name))


def _named_index(media: Media, name: str, studios: Sequence[Studio]) -> int | None:
    """Индекс по целому имени, снисходительно только к регистру и пробелам."""
    wanted = "".join(name.casefold().split())
    for track in media.tracks:
        label = "".join(track.label.casefold().split())
        studio = track_studio(media, track.index, studios)
        named = "".join(studio.name.casefold().split()) if studio is not None else ""
        if label == wanted or named == wanted:
            return track.index
    return None


def _ask_voice(media: Media, native: bool = False, studios: Sequence[Studio] = ()) -> int:
    """Меню озвучек — только по ``--voice`` без номера. Дефолт тот же, что и без флага."""
    default = media.default_track(native)
    if len(media.tracks) == 1:  # выбора нет - вопроса тоже
        return default
    _console_port().write(voices_table(media, default, studios=studios))
    return _console_port().choose(phrase("rank.voice_question"), len(media.tracks), default + 1) - 1
