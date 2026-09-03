"""Зеркало :mod:`torrcast.domain.facts.in_budget`: порции имён под предел одного запроса."""

from torrcast.domain.facts.in_budget import in_budget


def test_a_batch_is_cut_by_the_count_of_names() -> None:
    """Порция не длиннее предела API; пустая очередь не даёт ни одной порции."""
    assert list(in_budget(["a", "b", "c"], 2, 10_000)) == [["a", "b"], ["c"]]
    assert list(in_budget([], 50, 10_000)) == []


def test_russian_names_are_cut_by_the_length_of_the_future_address() -> None:
    """🔴 Полсотни русских имён в один адрес не влезают: Википедия отвечает на них 414.

    Считается тут не длина строки, а длина будущего адреса: русская буква занимает в нём
    шесть знаков вместо одного, и порция, годная по счёту имён, уезжала в отказ, который
    для считавшего имена выглядел как «статей не нашлось».
    """
    names = ["Матрица: Перезагрузка"] * 50
    parts = list(in_budget(names, 50, 6000))
    assert len(parts) > 1, "порция по счёту имён прошла бы, а по длине адреса - нет"
    assert all(sum(len(one.encode("utf-8")) * 3 + 3 for one in part) <= 6000 for part in parts)
    assert [one for part in parts for one in part] == names, "имена не потерялись"


def test_a_name_too_long_by_itself_still_goes_and_is_not_dropped() -> None:
    """Не влезающее в бюджет имя уезжает своей порцией: пусть ответит сервер, а не тишина."""
    assert list(in_budget(["x" * 5000], 50, 100)) == [["x" * 5000]]
