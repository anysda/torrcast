"""Разобранная командная строка ``cast``: что человек назвал и какая это команда.
Собирает её :func:`torrcast.cli.parse_args.parse_args`, читают команды пакета
:mod:`torrcast.cli`.
"""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.domain.episode import Episode
from torrcast.domain.split_episode import split_episode


@dataclass(slots=True)
class Args:
    query: list[str]
    #: ``--tv <ip>`` - запомнить адрес; ``--tv`` без адреса
    #: (:data:`~torrcast.cli.parse_args.TV_MENU`) - найти приёмники в сети и спросить,
    #: какой из них телевизор.
    tv: str | None = None
    release: int | None = None
    #: Инфохэш под номером из последнего ``cast releases``. Внутреннее поле: поздняя
    #: выдача меняет места, но не имеет права менять явно названную раздачу.
    release_hash: str = ""
    #: ``--pick N`` - картина N из меню, вопрос «Что смотрим?» не задаётся. Номер называет
    #: человек по списку на экране: молчаливой подмены тут не бывает, а без терминала это
    #: единственный способ назвать картину неинтерактивному запуску.
    pick: int | None = None
    #: ``--menu`` - поднять меню выбора картины: зритель называет, ЧТО играть, а не
    #: «где я остановился». Закладка на такой запрос не отвечает, и список поднимается
    #: даже там, где о выборе сказать нечего
    #: (:func:`~torrcast.usecases.choice.certain_default.certain_default`): без флага
    #: подходящую картину прибор берёт сам, а флаг - это и есть просьба показать другие.
    menu: bool = False
    file: int | None = None
    #: ``--voice N`` - играть дорожку N; ``--voice`` без номера (:data:`VOICE_MENU`) -
    #: показать меню озвучек и спросить. На счастливом пути обоих нет: озвучка
    #: выбирается сама.
    voice: int | None = None
    from_start: bool = False
    dry: bool = False
    #: ``cast log --since 2d|12h|30m|ГГГГ-ММ-ДД`` - с какого момента показывать след.
    since: str | None = None
    #: Внутреннее: показ внутри transient-юнита, руками не зовётся.
    play_key: str | None = None

    @property
    def command(self) -> str:
        """``stop`` / ``status`` / ``doctor`` / ``releases`` / ``voices`` / ``play`` /
        ``configure`` / ``worker``.
        """
        if self.play_key:
            return "worker"
        words = {"stop", "status", "doctor", "releases", "voices", "log"}
        if self.query and self.query[0] in words:
            return self.query[0]
        if not self.query:
            return "configure" if self.tv else "status"
        return "play"

    @property
    def episode(self) -> Episode | None:
        """Явно указанная серия: ``cast киберпанк s2e5``, ``2x5``, «2 сезон 5 серия»."""
        return split_episode(" ".join(self.query))[1]

    @property
    def title_query(self) -> str:
        """Запрос без указания серии: искать надо «киберпанк», а не «киберпанк 2x5»."""
        return split_episode(" ".join(self.query))[0]

    @property
    def pinned(self) -> bool:
        """Релиз или файл названы руками — отладочный путь, подмен в нём не бывает."""
        return self.release is not None or self.file is not None

    @property
    def from_menu(self) -> bool:
        """Картину называет меню, а не закладка: ``--menu`` или ``--pick N``.

        Оба - запрос «дай выбрать», и отвечать на него сохранённым местом нельзя:
        закладка знает лишь место ВНУТРИ однажды взятой картины.
        """
        return self.menu or self.pick is not None
