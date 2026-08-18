"""Серии выбранной раздачи: файлы к номерам, нужный файл и честный отказ.

Чистое правило без раздачи и сети: спрашивают его и отбор
(:mod:`torrcast.usecases.select`), и добор (:mod:`torrcast.usecases.reinforce`).
"""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.domain.episode import Episode
from torrcast.domain.episode_file import EpisodeFile
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

    def choose(self, release: Release, files: list[TorrFile]) -> TorrFile:
        """Файл нужной серии; такой серии в раздаче нет — честная строка со списком.

        🔴 Разбор серий тут НИЧЕГО не запоминает на себе. Один и тот же ``_Series`` живёт
        на всю картину, а спрашивают его параллельно: подготовка греет впрок и запасные
        раздачи (:meth:`torrcast.usecases.select_bench._Bench.spare`), и каждая зовёт этот же
        метод из своего потока. Стоило разбору лечь полем на объект - список серий
        картины оставляла ПОСЛЕДНЯЯ ответившая раздача, а не та, которую играют. У пака
        «Рик и Морти» (21 серия) в состояние уезжал пустой список от запасной раздачи, и
        сериал переставал быть сериалом: автоперехода на следующую серию не было вовсе.
        """
        found_files = map_episodes(files, release.season)
        found = next((f for f in found_files if f.at == self.want), None)
        if found is None:
            raise NotFoundError(self._miss_reason(release, found_files))
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
        (:attr:`~torrcast.parse.Release.season` / :attr:`~torrcast.parse.Release.seasons`),
        либо перечислила серии, не назвав сезона, — тот же признак, по которому
        сквозную линейку отличает :func:`torrcast.parse._run_span`. Раздача со сквозным
        счётом на просьбу о пятом сезоне не должна отвечать «серии нет»: серия там,
        скорее всего, ЕСТЬ — под сквозным номером, — и прежний ответ был неправдой
        дважды: и про наличие, и про причину. Поэтому здесь называются ОБЕ системы.
        """
        if (
            self.want.season > 1
            and release.episodes
            and release.season is None
            and not release.seasons
        ):
            span = f"{release.episodes[0]}-{release.episodes[-1]}"
            return (
                f"нумерации разные: {self.want} - это счёт по сезонам, а раздача считает "
                f"серии насквозь через весь сериал ({span}), не называя сезонов "
                f"({self.summary(files)}) - нужна раздача, подписанная сезоном: "
                "cast <запрос> --release N"
            )
        return (
            f"серии {self.want} в этой раздаче нет ({self.summary(files)}) - "
            "возьми другую раздачу: cast <запрос> --release N"
        )

    @staticmethod
    def table(files: list[TorrFile], season: int | None) -> list[list[int]]:
        """Список серий раздачи для состояния: по нему идут автопереход и прыжки.

        Спрашивается у той раздачи, которую играют, и разбирается заново - держать его
        на объекте нельзя (см. :meth:`choose`).
        """
        return [[f.season, f.episode, f.index] for f in map_episodes(files, season)]

    @staticmethod
    def summary(files: list[EpisodeFile]) -> str:
        """«серий 10: s1e1…s1e10», для пака — ещё и диапазон сезонов."""
        if not files:
            return "серий не нашлось"
        seasons = {f.season for f in files}
        span = f"сезоны {min(seasons)}-{max(seasons)} · " if len(seasons) > 1 else ""
        return f"{span}серий {len(files)}: {files[0].at}...{files[-1].at}"
