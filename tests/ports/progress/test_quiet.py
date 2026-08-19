"""Умолчание порта индикатора: принимает фазы и заметки и не печатает ничего."""

from torrcast.ports.progress.progress import Progress
from torrcast.ports.progress.quiet import Quiet


def test_the_quiet_bar_takes_every_phase_and_draws_nothing(capsys: object) -> None:
    """Прогон без композиционного корня ничего не рисует и не падает."""
    bar: Progress = Quiet()

    with bar as inner:
        inner.phase("поиск «моана»")
        inner.note("выбрана раздача")
        inner.stop()

    assert inner is bar, "умолчание отдаёт себя же, а не заводит второй индикатор"


def test_an_error_inside_the_phase_is_not_swallowed_by_the_quiet_bar() -> None:
    """Отрицательная проба: молчание не имеет права глотать ошибку сценария.

    ``__exit__`` умолчания возвращает ``None``, и это не мелочь: верни он ``True`` -
    и любая ошибка внутри фазы исчезла бы вместе с показом, а прогон остался бы зелёным.
    """
    try:
        with Quiet():
            raise ValueError("фаза сорвалась")
    except ValueError as exc:
        assert str(exc) == "фаза сорвалась"
    else:
        raise AssertionError("молчащий индикатор проглотил ошибку фазы")
