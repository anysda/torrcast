"""Сценарий ``cast --upgrade``: обновить продукт до последней версии, не гася показ.

Сама закачка тут не живёт и жить не может: её ведёт загрузчик ``install`` - тот же
файл, которым продукт ставится одностроком (:mod:`torrcast.ports.upgrade_environment`).
Здесь только то, чего загрузчик знать не вправе: идёт ли показ, и как об этом сказать.
"""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.exit_codes import EXIT_INFRA, EXIT_OK
from torrcast.ports.console import Console
from torrcast.ports.playback_session import PlaybackSession
from torrcast.ports.upgrade_environment import UpgradeEnvironment

#: 🔴 Урезанный каталог индексеров установщик отдаёт этим кодом штатно
#: (``EXIT_CATALOG_CUT`` в ``install.sh``): установка состоялась, но вышла беднее полной.
#: Обновление не вправе выдать его за провал - иначе всякий, кто ставил продукт с
#: неполным каталогом, получал бы «обновление не прошло» после успешного обновления.
CATALOG_CUT = 2


class Upgrade:
    """Сценарий команды ``cast --upgrade``.

    🔴 Обновление переставляет ровно тот venv, из которого работает зовущий процесс, и
    перезаписывает юниты, которыми держится показ. Поэтому порядок тут не украшение:
    сперва спрашивается экран, и только потом делается хоть что-нибудь. Погасить кино
    молча - худшее, что эта команда может сделать, и дешевле всего это предотвратить
    до первого сетевого запроса, а не отменять после.
    """

    def __init__(
        self,
        session: PlaybackSession,
        console: Console,
        environment: UpgradeEnvironment,
        version: str,
        language: str,
    ) -> None:
        self._session = session
        self._console = console
        self._environment = environment
        self._version = version
        self._language = language

    def run(self) -> int:
        refusal = self._refusal()
        if refusal:
            self._console.write(refusal)
            return EXIT_INFRA
        if not self._environment.is_root():
            # Прав нет, но есть чем их поднять: команда не падает с просьбой повторить
            # её руками, а повторяет себя сама. Пароль спросит сам sudo.
            self._console.write(phrase("upgrade.elevating"))
            return self._environment.elevate()
        loader = self._environment.loader()
        # Надписи разрешаются в строки ДО передачи работы загрузчику - и это не стиль.
        # 🔴 Пока идёт установка, pip сносит и переписывает файлы того самого пакета, из
        # которого работает этот процесс. Всё, что питон ещё не втянул, после возврата
        # он втягивал бы уже из перезаписанного дерева. Взятая заранее строка не просит
        # ни импорта, ни чтения каталога.
        failed = phrase("upgrade.failed", version=self._version)
        code = self._environment.hand_off(loader, self._version, self._language)
        if code not in (EXIT_OK, CATALOG_CUT):
            self._console.write(failed)
            return EXIT_INFRA
        return EXIT_OK

    def _refusal(self) -> str:
        """Почему обновляться нельзя прямо сейчас, либо пустая строка.

        Показ спрашивается ПЕРВЫМ: отказ по правам человек чинит одной командой и
        возвращается, а погашенная посреди серии картина не возвращается никак.
        """
        if self._playing():
            # 🔴 Имя показа берётся у записи состояния, а НЕ ТОЛЬКО у неё. Запись живёт
            # отдельным файлом и теряется (чистка /var, ход, писавший рядом), а юнит при
            # этом играет; спрошенный вслепую снимок отдал бы пусто, и человек прочёл бы
            # «сейчас играет «»» - отказ без причины. Описание живого юнита несёт то же
            # имя и переживает потерю записи, поэтому оно тут второй опорой, а не первой:
            # запись знает картину подробнее.
            key = self._session.key()
            shown = self._session.snapshot(key)
            what = (shown.shown_as if shown is not None else "") or key
            if not what:
                return phrase("upgrade.show_is_on_unnamed")
            return phrase("upgrade.show_is_on", what=what)
        if not self._environment.is_root() and not self._environment.can_elevate():
            # Отказ по правам остаётся отказом только там, где поднять их нечем: нет
            # sudo, либо им уже поднимались и root всё равно не вышел. Во всех остальных
            # случаях человеку тут говорить нечего - см. :meth:`run`.
            return phrase("upgrade.needs_root")
        if not self._environment.loader():
            return phrase("upgrade.no_loader")
        return ""

    def _playing(self) -> bool:
        """Есть ли прямо сейчас показ, который обновление оборвало бы.

        Живого юнита достаточно, и это НЕ та же мерка, что у ``cast status``: там
        отдельно спрашивают кадр, потому что отвечают человеку про экран. Тут вопрос
        другой - «есть ли что ронять», - и юнит, стоящий в темноте в ожидании
        вернувшегося источника, ронять так же нельзя, как играющий.
        """
        return self._session.active()
