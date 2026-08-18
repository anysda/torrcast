"""Слот назначенного завода индикатора: чем рисуется ход и кто это назначает."""

from torrcast.ports.progress import Progress, Quiet, factory, install, progress
from torrcast.ports.progress.slot import Slot


class _Spy(Quiet):
    seen: list[str] = []  # noqa: RUF012

    def phase(self, text: str) -> None:
        _Spy.seen.append(text)


def test_a_fresh_slot_draws_nothing_until_the_root_says_otherwise() -> None:
    """До слова композиционного корня ход рисует молчание."""
    slot = Slot()

    assert isinstance(slot.new(), Quiet)
    assert slot.factory() is Quiet


def test_the_slot_holds_the_factory_and_not_one_bar_for_the_whole_process() -> None:
    """Два вызова - два индикатора: вложенная фаза не имеет права гасить внешнюю."""
    _Spy.seen.clear()
    install(_Spy)

    first, second = progress(), progress()
    bar: Progress = first
    bar.phase("поиск")

    assert first is not second, "слот отдал один индикатор на весь процесс"
    assert factory() is _Spy
    assert _Spy.seen == ["поиск"]
    _Spy.seen.clear()


def test_the_public_name_is_a_function_and_not_the_module_beside_it() -> None:
    """Отрицательная проба: в пакете рядом лежит модуль ``progress`` с договором.

    Порядок реэкспорта в ``__init__`` решает, что достанется слоям - имя завода или
    модуль договора, - и ошибка тут молчаливая: падало бы уже на вызове.
    """
    assert callable(progress), "имя индикатора перекрыто модулем рядом"
