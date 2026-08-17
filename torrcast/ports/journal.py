"""Пишет диагностический след сценариев и отвечает на вопросы о нём.

Слои зовут след через этот порт, а не через модуль: `torrcast.trace` - это файлы и
фоновый писатель, то есть внешний мир. Кто именно пишет, решает композиционный корень
(:mod:`torrcast.runtime.wire`); до его слова след молчит - и это НЕ авария, а
умолчание: прогон без корня (щуп, отдельный тест) не обязан заводить файлы владельца.
"""

from __future__ import annotations

from typing import Any, Protocol


class Journal(Protocol):
    """Что сценариям нужно от следа - и ничего сверх того.

    Словарь событий именной, а не «пиши что хочешь»: имя события задаёт набор полей, по
    которым его потом ищет ``cast log``. Свободный :meth:`emit` остаётся для того, что
    именем ещё не названо.
    """

    def emit(self, phase: str, event: str, **fields: Any) -> None:
        """Положить произвольное событие в ленту."""

    def mark(self, name: str, **facts: Any) -> None:
        """Отметить фазу критического пути старта: где именно ушли секунды."""

    def shutdown(self) -> None:
        """Дождаться, пока фоновый писатель допишет хвост."""

    def records(self, since: float = 0.0) -> list[dict[str, Any]]:
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

    def skew(self, slot: int, want: float, got: float, hole: bool, src: str = "") -> None:
        """Расхождение сетки: какой кусок просили и какой отдали."""

    def warmth(self, event: str, secs: float, dur: float, size: int, why: str = "") -> None:
        """Ход прогрева: сколько секунд фильма готово и во что это обошлось."""


class _Silent:
    """След, которого нет: прогон без композиционного корня ничего не пишет."""

    def emit(self, phase: str, event: str, **fields: Any) -> None:
        return None

    def mark(self, name: str, **facts: Any) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def records(self, since: float = 0.0) -> list[dict[str, Any]]:
        return []

    def session_id(self) -> str:
        return ""

    def start_session(self) -> str:
        return ""

    def health(self) -> tuple[bool, float, int]:
        return False, 0.0, 0

    def __getattr__(self, name: str) -> Any:
        """Любое именное событие молчащей ленты - тоже молчание."""
        return lambda *args, **fields: None


_journal: Journal = _Silent()


def journal() -> Journal:
    """Куда пишется след прямо сейчас."""
    return _journal


def install(sink: Journal) -> None:
    """Назначить, кто пишет след. Зовёт это только композиционный корень и тесты."""
    global _journal
    _journal = sink
