"""Порядок последней показанной таблицы раздач: файл рядом с состоянием."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.filesystem.state.write_atomic import _write_atomic
from torrcast.domain.info_hash import info_hash
from torrcast.domain.release import Release


class ReleasePins:
    """Что стояло под номером в таблице ``cast releases``: записать и спросить.

    Номер живёт ровно до следующей таблицы того же запроса, поэтому файл переписывается
    целиком, а не дополняется: показанное вчера под номером 2 сегодня значит другое.

    Помимо раздач таблица запоминает порядок самих картин и их имена: номер картины
    (``--pick M``) без такой записи - не адрес, а место в списке, чей состав гуляет
    от захода к заходу. По записи выбор сверяет, ТУ ли картину взял номер.

    Тот же порядок картин запоминает и меню обычного ``cast`` (:meth:`remember_menu`):
    номер пункта меню - тот же адрес, что номер картины в таблице. Раздач под номерами
    меню не показывает, поэтому таблицу раздач меню не переписывает.
    """

    def remember(self, query: str, shown: list[tuple[str, str, list[Release]]]) -> None:
        """Атомарно запомнить порядок последней таблицы этого запроса.

        ``shown`` - строки таблицы в показанном порядке: ключ картины, её имя для
        человека и раздачи в порядке их номеров.
        """
        _write_atomic(
            self._path(),
            {
                query: {
                    "order": [key for key, _name, _ranked in shown],
                    "names": {key: name for key, name, _ranked in shown},
                    "shown": {
                        key: [info_hash(release) for release in ranked]
                        for key, _name, ranked in shown
                    },
                }
            },
        )

    def remember_menu(self, query: str, shown: list[tuple[str, str]]) -> None:
        """Атомарно запомнить порядок картин показанного меню этого запроса.

        ``shown`` - пункты меню в показанном порядке: ключ картины и её имя для
        человека. Таблица раздач остаётся от последнего ``cast releases``: её номера
        человек видел, а порядка раздач под пунктами меню он не видел никогда -
        переписать таблицу им значило бы подменить адрес ``--release N``.
        """
        _write_atomic(
            self._path(),
            {
                query: {
                    "order": [key for key, _name in shown],
                    "names": dict(shown),
                    "shown": self._tables(query),
                }
            },
        )

    def recalled(self, query: str, picture: str, number: int) -> str:
        """Вернуть хэш, стоявший под номером в последней показанной таблице.

        Номера нет, файла нет, лежит чужое - пусто: по пустому имени показ ищет заново,
        а не берёт раздачу наугад.
        """
        tables = self._tables(query)
        ranked = tables.get(picture, [])
        if not isinstance(ranked, list) or not all(isinstance(item, str) for item in ranked):
            return ""
        return ranked[number - 1] if 1 <= number <= len(ranked) else ""

    def recalled_picture(self, query: str, number: int) -> tuple[str, str]:
        """Картина, стоявшая под номером в последней таблице: ключ и имя.

        Пустая пара - таблицы этого запроса не было, и сверять номер не с чем: такой
        ``--pick`` остаётся просто номером пункта, каким человек его и назвал.
        """
        saved = self._read(self._path()).get(query, {})
        if not isinstance(saved, dict):
            return "", ""
        order = saved.get("order", [])
        names = saved.get("names", {})
        if not isinstance(order, list) or not all(isinstance(key, str) for key in order):
            return "", ""
        if not isinstance(names, dict):
            names = {}
        if not 1 <= number <= len(order):
            return "", ""
        key = order[number - 1]
        name = names.get(key, "")
        return key, name if isinstance(name, str) else ""

    def _tables(self, query: str) -> dict[str, Any]:
        """Таблицы раздач запроса; старый формат (без порядка картин) читается тоже."""
        saved = self._read(self._path()).get(query, {})
        if not isinstance(saved, dict):
            return {}
        tables = saved.get("shown", saved)
        return tables if isinstance(tables, dict) else {}

    def _path(self) -> Path:
        return state_path().with_name("release-pins.json")

    def _read(self, path: Path) -> dict[str, Any]:
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}


#: Один файл на процесс: и печать таблицы, и разбор номера спрашивают его же.
pins: Final = ReleasePins()
