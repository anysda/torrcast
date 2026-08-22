"""Запись состояния показа: что смотрим, чем, с какого места и досмотрено ли.

Чистая модель без файлов: читает и пишет её файловое состояние
(:class:`torrcast.adapters.filesystem.state.state.State`). Начало записи - поля самого показа -
лежит в :class:`torrcast.domain._playing._Playing`, здесь остаётся место в сериале, учёт и
всё, что у записи спрашивают.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from torrcast.domain._playing import EntryKind as EntryKind
from torrcast.domain._playing import _Playing
from torrcast.domain.ending_reached import ending_reached
from torrcast.domain.json_model import json_model
from torrcast.domain.json_number import json_number
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue
from torrcast.domain.watch_ratios import WATCHED_RATIO

__all__ = ["Entry", "EntryKind"]


@dataclass(slots=True)
class Entry(_Playing):
    """Запись состояния: что смотрим, чем и с какого места."""

    season: int | None = None
    episode: int | None = None
    #: Серии раздачи по порядку: ``[сезон, серия, номер файла, размер файла]``. Это и есть кэш
    #: выбора: стык серий и прыжок на s2e5 обходятся без Prowlarr и без вопросов.
    episodes: list[list[int]] = field(default_factory=list)
    #: Slug исходного запроса: по нему resume находит запись, не ходя в Prowlarr.
    query: str = ""
    #: Досмотрено. У фильма это конец истории, у сериала - повод взять следующую.
    done: bool = False
    updated: str = ""

    @property
    def ending(self) -> bool:
        """Дошёл ли показ до титров: место записи за долей её длительности.

        Правило одно на весь показ и живёт отдельно
        (:func:`torrcast.domain.ending_reached.ending_reached`): и запись, и приёмник обязаны
        отвечать на «дошло ли до конца» одинаково, иначе страховка перехода становится
        лотереей. Там же сказано, почему доля щедрая и почему неизвестная длительность -
        это «не конец».
        """
        return ending_reached(self.pos, self.dur)

    @property
    def watched(self) -> bool:
        """Досмотрена ли сохранённая закладка: позиция >= 95 % всей картины.

        Неизвестная длительность не даёт права угадывать долю. Нулевая позиция также
        никогда сюда не попадает: IDLE-приёмник сообщает ноль уже после показа, а
        сторож сохраняет последнюю положительную позицию живого сеанса.
        """
        return self.dur > 0 and self.pos > 0 and self.pos >= self.dur * WATCHED_RATIO

    @property
    def resumable(self) -> bool:
        """Есть ли что продолжать: недосмотренный прогресс."""
        return self.pos > 0 and not self.done

    @property
    def serial(self) -> bool:
        """Правда ли это сериал: тип ``tv`` и в раздаче **несколько** серий.

        Одна серия в списке — это не сериал, а осечка разбора: так в состоянии осталась
        «Moana 2», которую ``x264`` в имени сделал s1e1. Парсер починен, но записи-то
        остались, и строки «Серии: серий 1: s1e1…s1e1» в выводе фильма быть не должно
        ни у кого. Настоящей раздаче с одной серией это ничего не стоит: переходить
        всё равно некуда.
        """
        return self.kind == "tv" and len(self.episodes) > 1

    @property
    def label(self) -> str:
        """Подпись серии ``s1e2``; у фильма — пусто."""
        if not self.serial or self.season is None or self.episode is None:
            return ""
        return f"s{self.season}e{self.episode}"

    @property
    def shown_as(self) -> str:
        """Как показ зовёт эту картину человеку: «Название» с подписью серии."""
        return f"«{self.title}»" + (f" {self.label}" if self.label else "")

    def where(self, season: int, episode: int) -> int:
        """Место серии в списке серий раздачи; ``-1`` — такой серии в раздаче нет."""
        for at, item in enumerate(self.episodes):
            if len(item) >= 2 and item[0] == season and item[1] == episode:
                return at
        return -1

    def jump(self, season: int, episode: int) -> Entry | None:
        """Прыжок на серию в пределах уже выбранной раздачи: ни поиска, ни вопросов.
        Серии в раздаче нет — ``None``, и цепочка честно идёт искать релиз нужного сезона.
        """
        at = self.where(season, episode)
        if at < 0:
            return None
        return self._go(at)

    def advance(self) -> Entry:
        """Что записать по достижении порога перехода: фильму — пометка «досмотрено» и
        сброс позиции (следующий ``cast`` начнёт сначала), сериалу — следующая серия
        раздачи с нуля, выбор релиза и дорожки при этом сохраняется. Серия была
        последней — «досмотрено» и для сериала: конец сезона или конец раздачи.

        Прогрев (``warm``) переход не переживает: досмотренному его стирает с диска
        сам выход показа, а прогретое следующей серии лежит в своём хранилище и своё
        число придёт от её сторожа - чужое здесь было бы враньём наружу. Отметка темноты
        (``dark``) не переживает по той же причине: она про экран, который погас на
        ПРОШЛОМ файле.
        """
        at = self.where(self.season or 0, self.episode or 0)
        if self.kind == "tv" and 0 <= at < len(self.episodes) - 1:
            return self._go(at + 1)
        return replace(self, pos=0.0, done=True, warm=0.0, dark=0.0, dark_why="")

    def _go(self, at: int) -> Entry:
        """Встать на серию номер ``at`` списка: новый файл, позиция, длительность,
        прогрев и отметка темноты с нуля - всё это относится к файлу, а файл теперь
        другой."""
        season, episode, file_idx = self.episodes[at][:3]
        return replace(
            self,
            season=season,
            episode=episode,
            file_idx=file_idx,
            pos=0.0,
            dur=0.0,
            done=False,
            warm=0.0,
            dark=0.0,
            dark_why="",
        )

    def touch(self) -> Entry:
        """Копия записи со свежей меткой времени."""
        return replace(self, updated=datetime.now(UTC).astimezone().isoformat())

    @classmethod
    def from_json(cls, data: Mapping[str, JsonValue]) -> Entry:
        """Запись из разобранного JSON состояния; незнакомые ключи молча теряются."""
        fields = dict(data)
        raw = fields.get("episodes")
        if isinstance(raw, list):  # битую строку списка серий лучше потерять, чем упасть
            fields["episodes"] = [
                [int(json_number(n)) for n in json_rows(item)[:4]]
                for item in raw
                if isinstance(item, list) and len(item) >= 3
            ]
        return json_model(cls, fields, cls.__dataclass_fields__)
