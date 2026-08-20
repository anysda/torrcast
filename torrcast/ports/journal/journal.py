"""Пишет диагностический след сценариев и отвечает на вопросы о нём.

Слои зовут след через этот порт, а не через модуль: лента - это файлы и фоновый
писатель, то есть внешний мир. Кто именно пишет, решает композиционный корень
(:mod:`torrcast.runtime.wire`); до его слова след молчит - и это НЕ авария, а
умолчание: прогон без корня (щуп, отдельный тест) не обязан заводить файлы пользователя.
"""

from __future__ import annotations

from typing import Protocol

from torrcast.ports.json_value import JsonValue


class Journal(Protocol):
    """Что сценариям нужно от следа - и ничего сверх того.

    Словарь событий именной, а не «пиши что хочешь»: имя события задаёт набор полей, по
    которым его потом ищет ``cast log``. Свободный :meth:`emit` остаётся для того, что
    именем ещё не названо.

    Поля события названы :data:`~torrcast.ports.json_value.JsonValue`, а не «чем угодно»:
    запись уезжает в ленту строкой ``jsonl``, и всё, что в JSON не укладывается, лента
    роняет целиком вместе с записью. Договор тут ровно тот, который лента и так
    исполняет, - просто теперь он назван.
    """

    def emit(self, phase: str, event: str, **fields: object) -> None:
        """Положить произвольное событие в ленту.

        ⚠️ Поля тут пока шире правды: настоящий договор свободного события - такой же
        :data:`~torrcast.ports.json_value.JsonValue`, как у :meth:`mark`, но один слот
        сценария рабочего (``_worker_thresholds``) объявлен ``dict[str, object]`` и
        разливается сюда звёздочкой. Сузить его - правка в слое сценариев, и она идёт
        отдельно от этого куска.
        """

    def mark(self, name: str, **facts: JsonValue) -> None:
        """Отметить фазу критического пути старта: где именно ушли секунды."""

    def shutdown(self) -> None:
        """Дождаться, пока фоновый писатель допишет хвост."""

    def records(self, since: float = 0.0) -> list[dict[str, JsonValue]]:
        """Записи ленты, начиная с указанного момента."""

    def session_id(self) -> str:
        """Идентификатор сеанса: им склеиваются поиск, отбор и показ одной команды."""

    def start_session(self) -> str:
        """Начать новый сеанс и вернуть его идентификатор."""

    def health(self) -> tuple[bool, float, int]:
        """Жива ли лента, когда писали последний раз и сколько места занято."""

    def nudge(self, pos: float, to: float, hit: int, stuck: float, front: float) -> None:
        """Подталкивание приёмника, застрявшего на месте."""

    def segment(self, slot: int, mb: float, sent: float, wait: float, src: str) -> None:
        """Отдача куска приёмнику: сколько весил, сколько ехал."""

    def plan(self, pack: str, warm: str, spots: int, preset: str = "", mbit: float = 0.0) -> None:
        """План показа: чем пакуем, что греем, сколько мест."""

    def reload(self, pos: float, tries: int, error: int | None = None) -> None:
        """Перезапуск показа с той же позиции."""

    def offline(self, why: str, asked: bool = False) -> None:
        """Внешняя служба не ответила."""

    def resupply(self, torrent: str, ok: bool) -> None:
        """Повторная подача раздачи в TorrServer."""

    def dark(self, pos: float, why: str, shown: bool = True) -> None:
        """Экран погас: с какой секунды и по какой причине."""

    def revive(self, pos: float, tries: int, waited: float, ok: bool) -> None:
        """Попытка поднять погасший показ."""

    def seek(self, frm: float, to: float, wait: float | None, why: str = "") -> None:
        """Перемотка: откуда, куда и сколько ждали картинки."""

    def evict(self, key: str, freed: int, need: int, title: str = "") -> None:
        """Уборка прогретого ради места."""

    def freeze(
        self, pos: float, lost: float, secs: float, total: float, front: float, state: str
    ) -> None:
        """Подгруз: картинка стояла, хотя приёмник называл себя играющим."""

    def skew(self, slot: int, want: float, got: float, hole: bool, src: str = "") -> None:
        """Расхождение сетки: какой кусок просили и какой отдали."""

    def warmth(self, event: str, secs: float, dur: float, size: int, why: str = "") -> None:
        """Ход прогрева: сколько секунд фильма готово и во что это обошлось."""
