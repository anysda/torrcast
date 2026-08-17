"""Стенд команды показа: трекеры, служба раздач, юнит, прогрев и человек - одним объектом.

Команда показа берёт эти зависимости из своего модуля, а не из конструктора: разрез до
неё ещё не дошёл. Поэтому стенд один раз ставит на их место переходники, которые в момент
вызова спрашивают ЭТОТ объект, - и тест собирает мир полями, а не подменами по месту.
Когда у команды появится композиционный корень, менять придётся только этот файл.

Юнит показа - уже не подмена: он ставится на свой порт (:mod:`torrcast.ports.show_unit`),
и это видно по единственному звену, которое стенд отдаёт объектом, а не именем модуля.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest

from torrcast import cli, console
from torrcast.ports import show_unit as unit_port
from torrcast.usecases import playback


@dataclass
class _WorldShowUnit:
    """Юнит показа этого стенда: отвечает полями мира, а не systemd.

    Ставится он на порт (:mod:`torrcast.ports.show_unit`), а не подменой имени в модуле:
    у юнита разрез уже прошёл, и стенду незачем знать, каким именем показ спрашивал бы
    systemd. Возвращает порт на место фикстура ``_ports_restored``.
    """

    world: CastWorld

    def active(self) -> bool:
        return self.world.playing

    def why(self) -> str:
        return "юнита на стенде нет"

    def stop(self) -> None:
        self.world.stops += 1

    def key(self) -> str:
        return self.world.key


@dataclass
class CastWorld:
    """Внешний мир одного прогона команды ``cast``.

    Поля делятся на две части: чем мир отвечает (индексатор, служба раздач, паспорт,
    ответы человека, живость юнита) и что он запомнил (вопросы, запуски, остановки).
    """

    #: Класс индексатора: его команда заводит сама, отдавая адрес и ключ.
    indexer: Any = None
    #: Класс службы раздач: заводится по адресу, отвечает про раздачу и её файлы.
    torrents: Any = None
    #: Паспорт файла (``probe``): дорожки и длительность без единого запроса в рой.
    passport: Callable[..., Any] | None = None
    #: Что отвечает человек на вопросы по порядку; кончились - дальше пустой Enter.
    answers: list[str] = field(default_factory=list)
    #: Терминал ли перед нами: без него меню не спрашивается вовсе.
    tty: bool = True
    #: Идёт ли показ прямо сейчас и под каким ключом - ответ юнита показа.
    playing: bool = False
    key: str = ""
    #: Чем заняться вместо ожидания картинки и прогрева места; ``None`` - ничем.
    await_playing: Callable[..., Any] | None = None
    warm: Callable[..., Any] | None = None

    #: Заданные вопросы, ключи запущенных показов и число остановок юнита.
    questions: list[str] = field(default_factory=list)
    started: list[str] = field(default_factory=list)
    stops: int = 0
    awaited: int = 0
    warmed: int = 0

    def install(self, patch: pytest.MonkeyPatch) -> None:
        """Поставить переходники на место зависимостей команды показа."""
        patch.setattr(cli, "Prowlarr", self._indexer)
        patch.setattr(cli, "TorrServer", self._torrents)
        patch.setattr(cli, "probe", self._probe)
        patch.setattr(playback, "start_play_unit", self._start)
        unit_port.install(_WorldShowUnit(self))
        patch.setattr(cli, "_await_playing", self._await)
        patch.setattr(cli, "warm_file", self._warm)
        patch.setattr(console, "stdin_is_tty", lambda: self.tty)
        patch.setattr("builtins.input", self.ask)

    def ask(self, prompt: str = "") -> str:
        """Ответ человека: вопрос запоминается, ответ берётся из очереди."""
        self.questions.append(prompt)
        return self.answers.pop(0) if self.answers else ""

    def asked(self) -> list[str]:
        """Заданные вопросы без хвоста с умолчанием - по ним и сверяют разговор."""
        return [question.split("[")[0].strip() for question in self.questions]

    def _indexer(self, url: str, apikey: str = "") -> Any:
        assert self.indexer is not None, "индексатор стенду не задан"
        return self.indexer(url, apikey)

    def _torrents(self, url: str, timeout: float = 30.0) -> Any:
        assert self.torrents is not None, "служба раздач стенду не задана"
        return self.torrents(url)

    def _probe(self, url: str, timeout: float = 90.0, alive: Any = None) -> Any:
        assert self.passport is not None, "паспорт файла стенду не задан"
        return self.passport(url, timeout=timeout, alive=alive)

    def _start(self, key: str) -> None:
        """Показ уехал в юнит. Живым мир от этого не становится: живость задаёт тест -
        иначе второй запуск подряд видел бы юнит, которого на стенде нет.
        """
        self.started.append(key)

    def _await(self, config: Any, progress: Any, timeout: float = 120.0) -> None:
        self.awaited += 1
        if self.await_playing is not None:
            self.await_playing(config, progress, timeout)

    def _warm(self, *args: Any, **kwargs: Any) -> Any:
        self.warmed += 1
        return self.warm(*args, **kwargs) if self.warm is not None else None
