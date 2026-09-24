"""Серии выбранной раздачи: файлы к номерам, нужный файл и честный отказ.

Чистое правило без раздачи и сети: спрашивают его и отбор
(:mod:`torrcast.usecases.select`), и добор (:mod:`torrcast.usecases.reinforce`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.episode import Episode
from torrcast.domain.episode_absent_error import EpisodeAbsentError
from torrcast.domain.episode_file import EpisodeFile
from torrcast.domain.episode_ordinal import EpisodeOrdinal
from torrcast.domain.map_episodes import map_episodes
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile


@dataclass(slots=True)
class _Series:
    """Серии выбранной раздачи: файлы → ``sNeM``, нужный файл и кэш для состояния.

    Пак это или один сезон — решают ФАЙЛЫ, а не имя раздачи: сколько сезонов нашлось в
    путях, столько и будет в списке, и прыжок `s2e5` внутри пака обойдётся без поиска.
    """

    want: Episode
    #: Числа серий сезонов списка, в котором человек выбрал серию, когда это не нумерация
    #: раздач: ``want`` тогда сквозной номер ``s1eN`` (:mod:`torrcast.domain.episode_ordinal`).
    layout: EpisodeOrdinal | None = None
    #: Серия, как её назвала строка списка: ею говорит отказ.
    shown: Episode | None = None

    @classmethod
    def asked(cls, want: Episode, layout: EpisodeOrdinal | None = None) -> _Series:
        """Серия запроса; строка чужой раздачам нумерации ищется сквозным номером."""
        ordinal = layout.want(want) if layout is not None else None
        return cls(ordinal, layout, want) if ordinal is not None else cls(want)

    def choose(self, release: Release, files: list[TorrFile]) -> TorrFile:
        """Файл нужной серии; такой серии в раздаче нет — честная строка со списком.

        🔴 Разбор серий тут НИЧЕГО не запоминает на себе. Один и тот же ``_Series`` живёт
        на всю картину, а спрашивают его параллельно: подготовка греет впрок и запасные
        раздачи (:meth:`torrcast.usecases.select_bench.bench.Bench.spare`), и каждая зовёт этот же
        метод из своего потока. Стоило разбору лечь полем на объект - список серий
        картины оставляла ПОСЛЕДНЯЯ ответившая раздача, а не та, которую играют. У пака
        «Рик и Морти» (21 серия) в состояние уезжал пустой список от запасной раздачи, и
        сериал переставал быть сериалом: автоперехода на следующую серию не было вовсе.
        """
        found_files = self.found(release, files)
        if self.layout is not None:
            found = self.layout.find(found_files, self.want.episode)
        else:
            found = next((f for f in found_files if f.at == self.want), None)
        if found is None:
            reason = self._miss_reason(release, found_files)
            seasons = {file.season for file in found_files}
            in_season = [file.episode for file in found_files if file.season == self.want.season]
            complete_pack = len(release.seasons) > 1 and set(release.seasons) <= seasons
            if complete_pack and in_season and self.want.episode > max(in_season):
                raise EpisodeAbsentError(reason, self.want.season, max(in_season))
            raise NotFoundError(reason)
        return next(f for f in files if f.index == found.index)

    def _miss_reason(self, release: Release, files: list[EpisodeFile]) -> str:
        """Текст отказа: серии правда нет — или раздача считает в ДРУГОЙ системе.

        🔴 TC-182. У одного сериала сосуществуют ДВЕ нумерации: у «Гинтамы» 38 раздач
        подписаны сезонами S05-S10 (нумерация стриминга), а куски RuTor — сквозным
        счётом через весь сериал (``[01-201]``, ``[202-252]``, ``[253-265]``). Это
        РАЗНЫЕ номера: s5e1 по-стриминговому живёт где-то внутри сквозного 202-252, а
        вычислить, где именно, нельзя честно — границ сезонов не назвало ни одно имя,
        и любой пересчёт был бы выдумкой.

        Признак системы — настоящий и лежит в имени раздачи: сезон она либо назвала
        (:attr:`~torrcast.domain.release.Release.season` /
        :attr:`~torrcast.domain.release.Release.seasons`), либо перечислила серии, не назвав сезона,
        — тот же признак, по которому сквозную линейку отличает
        :func:`torrcast.domain.run_span._run_span`. Раздача со сквозным счётом на просьбу о пятом
        сезоне не должна отвечать «серии нет»: серия там, скорее всего, ЕСТЬ — под сквозным номером,
        — и прежний ответ был неправдой дважды: и про наличие, и про причину. Поэтому здесь
        называются ОБЕ системы.
        """
        if self.shown is not None:
            return phrase("series.episode_absent", want=self.shown, summary=self.summary(files))
        if (
            self.want.season > 1
            and release.episodes
            and release.season is None
            and not release.seasons
        ):
            span = f"{release.episodes[0]}-{release.episodes[-1]}"
            return phrase(
                "series.numbering_differs",
                want=self.want,
                span=span,
                summary=self.summary(files),
            )
        return phrase("series.episode_absent", want=self.want, summary=self.summary(files))

    @staticmethod
    def found(release: Release, files: list[TorrFile]) -> list[EpisodeFile]:
        """Серии раздачи так, как их видит ПОКАЗ: без нумерации, которой он не поверит."""
        return map_episodes(files, release.season, by_order=False) or _in_order(release, files)

    @staticmethod
    def table(files: list[TorrFile], release: Release) -> list[list[int]]:
        """Список серий раздачи для состояния и для строк карточки.

        Спрашивается у той раздачи, которую играют, и разбирается заново - держать его
        на объекте нельзя (см. :meth:`choose`). Разбор ТОТ ЖЕ, которым показ выбирает
        файл: строка, которой показ не сыграет, не должна рисоваться вовсе. «Классический
        Доктор Кто» S1E1-43 отдавал 38 строк, размеченных по порядку файлов, и каждая
        кончалась «серии s1e1 в этой раздаче нет (серий не нашлось)».
        """
        return [[f.season, f.episode, f.index, f.size] for f in _Series.found(release, files)]

    @staticmethod
    def summary(files: list[EpisodeFile]) -> str:
        """«серий 10: s1e1…s1e10», для пака — ещё и диапазон сезонов."""
        if not files:
            return phrase("series.none_found")
        seasons = {f.season for f in files}
        span = (
            phrase("series.seasons_span", first=min(seasons), last=max(seasons))
            if len(seasons) > 1
            else ""
        )
        return phrase(
            "series.episode_count",
            span=span,
            count=len(files),
            first=files[0].at,
            last=files[-1].at,
        )


def _in_order(release: Release, files: list[TorrFile]) -> list[EpisodeFile]:
    """Серии по порядку файлов - только там, где порядок и есть номер.

    Пак «S1-4, 1-72» с файлами «1ACV01» по порядку отдавал на s1e1 первый файл первого
    сезона, а «[1061-1112 из XX]» на s1e1 - серию 1061. Сезоны, разложенные каталогами,
    порядку верят; иначе имя с несколькими сезонами не верит, а названная линейка серий
    верит, только если файлов ровно столько.
    """
    ordered = map_episodes(files, release.season)
    if len({f.season for f in ordered}) > 1:
        return ordered
    if len(release.seasons) > 1 or (release.episodes and len(ordered) != len(release.episodes)):
        return []
    if not release.episodes:
        return ordered
    return [replace(f, episode=n) for f, n in zip(ordered, release.episodes, strict=True)]
