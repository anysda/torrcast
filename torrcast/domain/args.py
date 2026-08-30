"""Разобранная командная строка ``cast``: что человек назвал и какая это команда.
Собирает её :func:`torrcast.cli.parse_args.parse_args`, читают команды пакета
:mod:`torrcast.cli`.
"""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.domain.episode import Episode
from torrcast.domain.magnet_hash import magnet_hash
from torrcast.domain.split_episode import split_episode


@dataclass(slots=True)
class Args:
    query: list[str]
    #: ``--tv <ip>`` - запомнить адрес; ``--tv`` без адреса
    #: (:data:`~torrcast.cli.parse_args.TV_MENU`) - найти приёмники в сети и спросить,
    #: какой из них телевизор.
    tv: str | None = None
    #: ``-tg`` без значения поднимает нелинейное меню настройки Telegram.
    telegram: bool = False
    #: ``--ru`` / ``--en`` - язык, названный в этом запуске. ``None`` значит «не назван»:
    #: тогда язык берётся из настройки (:attr:`torrcast.domain.config.Config.language`), а
    #: не подменяется английским. Флаг не режим одного запуска, он ЗАПОМИНАЕТСЯ
    #: (:mod:`torrcast.cli.language`).
    language: str | None = None
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
    #: ``--voice N`` - играть дорожку N; ``--voice ИМЯ`` - взять студию; ``--voice``
    #: без значения (:data:`VOICE_MENU`) - показать меню озвучек и спросить. На
    #: счастливом пути флага нет: озвучка выбирается сама.
    voice: int | str | None = None
    from_start: bool = False
    dry: bool = False
    #: ``cast log --since 2d|12h|30m|ГГГГ-ММ-ДД`` - с какого момента показывать след.
    since: str | None = None
    #: Внутреннее: показ внутри transient-юнита, руками не зовётся.
    play_key: str | None = None
    #: Имя раздачи, которая в ЭТОМ запуске уже признана неиграющей
    #: (:func:`torrcast.usecases.select._dead_release._dead_release`). Внутреннее поле и
    #: живёт ровно один запуск: следующий спросит рой заново, потому что сиды возвращаются.
    #:
    #: 🔴 Без него отбор поднял бы тот же верх выдачи, и зритель получил бы ту же
    #: темноту второй раз подряд - уже зная её причину.
    dead_hash: str = ""

    def bury(self, magnet: str) -> None:
        """Запомнить раздачу, которая в этом запуске не сыграла.

        Запоминается ИМЯ (инфохэш), а не строка магнита: в выдаче нового поиска у той же
        раздачи другие трекеры и другое ``dn``, и сверять её было бы нечем. Магнит без
        имени сверяется сам с собой - хуже точного имени, но лучше молчания.
        """
        self.dead_hash = magnet_hash(magnet) or magnet

    def buried(self, magnet: str) -> bool:
        """Правда ли, что эту раздачу в этом запуске уже похоронили.

        Пустое имя тут не совпадает ни с чем: магнит, не назвавший себя, не повод
        выкинуть из отбора всех остальных таких же.
        """
        return bool(self.dead_hash) and (magnet_hash(magnet) or magnet) == self.dead_hash

    @property
    def command(self) -> str:
        """``stop`` / ``status`` / ``doctor`` / ``releases`` / ``voices`` / ``play`` /
        ``configure`` / ``worker``.
        """
        if self.play_key:
            return "worker"
        if self.telegram:
            return "telegram"
        # Голый `cast --ru` - это вся работа: переключить язык, сказать об этом и выйти
        # нулём. Пустой запрос иначе означал бы «покажи состояние», и человек, назвавший
        # язык, получил бы вместо ответа сводку показа. Названная рядом работа флагом не
        # отменяется: `cast --ru мумия` играет мумию (:func:`torrcast.cli.main.main`).
        if self.language is not None and not self.query and self.tv is None:
            return "language"
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
