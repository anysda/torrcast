"""Какую дорожку играем и что после этого лежит в памяти картины; зовёт запуск показа."""

from __future__ import annotations

from typing import Protocol

from torrcast.domain.infra_error import InfraError
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.rank_settings import VOICE_MENU
from torrcast.usecases.rank.configure import _console_port
from torrcast.usecases.rank.voices_table import voices_table


class _Voiced(Protocol):
    """Разобранная строка запуска в объёме, который нужен выбору дорожки: ``--voice N``.

    Полный :class:`torrcast.cli.args.Args` сюда не приходит: разбор аргументов стоит слоем
    выше сценариев, а выбору дорожки от него нужна одна ручка.
    """

    voice: int | None


def pick_voice(media: Media, args: _Voiced, remembered: str = "") -> tuple[int, str]:
    """Какую дорожку играем и что после этого лежит в памяти картины.

    **На счастливом пути вопроса про озвучку нет.** Дорожка выбирается сама
    (:meth:`Media.default_track`), и её подпись печатается в строке запуска —
    молчаливых подмен не бывает.

    Спросить можно только явно: ``--voice N`` берёт дорожку N, ``--voice`` без номера
    показывает меню. Оба — явный выбор, и только он пишется в память картины
    (:attr:`torrcast.domain.entry.Entry.voice`). Автовыбор память не трогает: иначе первый же
    запуск с другим релизом переписал бы то, что пользователь выбрал руками.

    Возвращает пару «номер дорожки в этом релизе, память картины».
    """
    if not media.tracks:
        raise InfraError("в файле нет звуковых дорожек")
    if args.voice is not None:
        index = _ask_voice(media) if args.voice == VOICE_MENU else _voice_number(media, args.voice)
        return index, media.tracks[index].label
    if remembered:
        found = media.find_voice(remembered)
        if found is not None:
            return found, remembered
        # Память живёт на картину, а релиз временный: озвучки в нём нет - говорим и
        # играем обычную, но выбор пользователя не забываем (:attr:`Entry.voice`).
        _console_port().write(f"озвучки «{remembered}» в этом релизе нет - беру обычную")
    return media.default_track(), remembered


def _voice_number(media: Media, number: int) -> int:
    """Номер дорожки от человека → индекс; чужого номера нет — честная строка."""
    if not 1 <= number <= len(media.tracks):
        raise NotFoundError(
            f"дорожек {len(media.tracks)}, номера {number} нет - посмотри: cast voices <запрос>"
        )
    return number - 1


def _ask_voice(media: Media) -> int:
    """Меню озвучек — только по ``--voice`` без номера. Дефолт тот же, что и без флага."""
    default = media.default_track()
    if len(media.tracks) == 1:  # выбора нет - вопроса тоже
        return default
    _console_port().write(voices_table(media, default))
    return _console_port().choose("Озвучка?", len(media.tracks), default + 1) - 1
