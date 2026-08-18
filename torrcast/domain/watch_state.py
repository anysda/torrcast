"""Состояние просмотра как значение: что записано и что из этого спрашивают.

Чистые правила без файла: читает и пишет его файловое состояние
(:class:`torrcast.adapters.filesystem.state.State`), а спрашивают - сценарии.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from torrcast.domain.entry import Entry
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index


@dataclass(slots=True)
class WatchState:
    """Состояние целиком: ключ ``<тип>:<slug>:<год>`` → :class:`Entry`."""

    entries: dict[str, Entry] = field(default_factory=dict)

    def get(self, key: str) -> Entry | None:
        return self.entries.get(key)

    def find(self, query: str) -> tuple[str, Entry] | None:
        """Запись по запросу пользователя, без похода в Prowlarr: сравниваем slug
        запроса с сохранённым запросом и со slug'ом в ключе; несколько — берём свежайшую.

        Запись, которая отвечает на другой вопрос, отсюда не возвращается вовсе
        (:func:`_other_part`): продолжать можно ту картину, которую назвали.
        """
        want = slugify(query)
        if not want:
            return None
        hits = [(k, e) for k, e in self.entries.items() if want in {e.query, _slug(k)}]
        # Сериал зовут коротко: «киберпанк» вместо «киберпанк бегущие по краю».
        # Фильму так нельзя: «матрица» - это запрос франшизы, а не «Матрица: Перезагрузка».
        hits = hits or [
            (k, e) for k, e in self.entries.items() if e.kind == "tv" and _slug(k).startswith(want)
        ]
        hits = [(k, e) for k, e in hits if not _other_part(query, want, k, e)]
        return max(hits, key=lambda item: item[1].updated) if hits else None

    def latest(self) -> tuple[str, Entry] | None:
        """Самая свежая запись — то, что показывает ``cast status``."""
        return max(self.entries.items(), key=lambda item: item[1].updated, default=None)

    def held(self) -> set[str]:
        """Хэши раздач, которые сейчас кто-то держит: непустой :attr:`Entry.torrent`.

        Счётчик владения по хэшу вырождается в множество: двух живых показов не бывает
        по устройству - юнит ``torrcast-play`` один на всю систему, и новый ``cast`` гасит
        прежний до своего старта (:func:`torrcast.stream.start_play_unit`). Поэтому
        раздача либо чья-то, либо ничья, и спрашивать «сколько держат» не приходится.

        Читает это уборка прогрева параллельного ``cast``: записанное сносить нельзя -
        это выдернет раздачу из-под живого показа. Гонки на записи тут нет, потому что
        писать нечего: операция одна, чтение, а отметку ставит и снимает один юнит.
        """
        return {entry.torrent for entry in self.entries.values() if entry.torrent}

    def showing(self) -> tuple[str, Entry] | None:
        """Показ, который идёт на приёмнике прямо сейчас, или ``None``.

        Признак тот же, что у :meth:`held`, - непустой :attr:`Entry.torrent`: отметку
        ставит юнит показа в ту же секунду, когда поднял раздачу, и снимает, когда её
        убрал. Двух живых показов не бывает по устройству, поэтому запись тут не больше
        одной; на всякий случай берётся свежайшая.

        🔴 Приёмник об этом НЕ спрашивается, и это правило, а не экономия: у всех
        соединений pychromecast один ``source_id``, поэтому второй опрашивающий процесс
        неотличим от владельца сессии и гасит живой показ
        (:class:`torrcast.cast.ChromecastReceiver`). Занятость телевизора мы знаем из
        своего состояния или не знаем вовсе.

        ⚠️ Чего этот признак НЕ видит: показ, убитый ``SIGKILL``, оставляет хэш записанным
        и выглядит отсюда живым. Разбирает такие сироты :func:`torrcast.cli._release_orphans`
        (он спрашивает systemd, а не приёмник) - и зовётся он до этой проверки.
        """
        live = [(key, entry) for key, entry in self.entries.items() if entry.torrent]
        return max(live, key=lambda item: item[1].updated) if live else None

    def put(self, key: str, entry: Entry) -> None:
        """Положить запись, обновив метку времени."""
        self.entries[key] = entry.touch()

    def drop(self, key: str) -> None:
        """Забыть запись по ключу."""
        self.entries.pop(key, None)

    def __iter__(self) -> Iterator[tuple[str, Entry]]:
        return iter(self.entries.items())


def _slug(key: str) -> str:
    """Slug канонического названия из ключа ``<тип>:<slug>:<год>``."""
    return key.split(":")[1] if ":" in key else ""


def _other_part(query: str, want: str, key: str, entry: Entry) -> bool:
    """Запись - другая часть франшизы, а не та картина, которую назвали.

    🔴 Сохранённая позиция отвечает на вопрос «где я остановился», а не «какую картину я
    прошу», - и стоять в очереди решений она обязана после выбора картины, а не перед
    ним. Записывается же рядом с позицией ТЕКСТ запроса (:attr:`Entry.query`), а он у
    имени франшизы общий на всю линейку: «Тачки 3», однажды выбранные по запросу «тачки»,
    отвечали потом на каждое «тачки» - молча, вопроса про картину не задавалось вовсе.
    Другое кино под знакомым именем - ровно та подмена, которой отбор не делает нигде
    (:func:`torrcast.usecases.choice.part_one_swap`), и продолжение делать её тоже не вправе.

    Спрашивается при этом НОМЕР, а не имя: имя у записи и у запроса живут на разных
    языках («Moana 2» под запросом «моана 2»), а номер части один на оба
    (:func:`~torrcast.parse.split_franchise_index`). Названный номер сошёлся с номером
    записи - назвали её и есть; номера нет ни там, ни там - речь об одной картине, и
    продолжение идёт как раньше. «Аполлон 13» на запрос «аполлон 13» тоже проходит:
    там номер назван, и он тот же самый.

    Имя остаётся запасной сверкой для записей, чей номер разбор в запросе не увидел:
    «моана-2» - это уже slug, пробела перед цифрой в нём нет.

    Сериала это правило не касается вовсе: его зовут коротко нарочно (:meth:`State.find`),
    и число в его названии - сезон, а не соседняя картина. «Кухня 6» на запрос «кухня»
    продолжает следующую невиденную серию, как и продолжала.

    Закладка при этом не теряется: у выбранной картины её предложат внутри
    (:func:`torrcast.cli._continue_picked`).
    """
    if entry.serial:
        return False
    part = split_franchise_index(entry.title)[1]
    if part is None or part == 1 or part == split_franchise_index(query)[1]:
        return False
    return want not in {_slug(key), slugify(entry.title)}
