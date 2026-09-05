"""Зеркало :mod:`torrcast.domain.richer_namesake`: кому уходит имя тощего тёзки."""

from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.richer_namesake import _richer_namesake, _whole_word


def _group(title: str, copies: int) -> Picture:
    return Picture(
        title=title,
        year=2001,
        releases=[Release(raw_name=title, title=title) for _ in range(copies)],
    )


def _groups(spec: dict[str, list[int]]) -> dict[str, list[Picture]]:
    """Группы франшиз: ключ - слаг, значение - раздачи каждой её картины."""
    return {key: [_group(key, copies) for copies in sizes] for key, sizes in spec.items()}


def test_a_namesake_the_catalogue_barely_knows_yields_to_the_richer_franchise() -> None:
    """🔴 Живой замер стенда: «властелин» - одна картина в одну раздачу против 12 и 169."""
    groups = _groups({"властелин": [1], "властелин-колец": [35, 36, 30, 22, 20, 19, 7]})

    assert _richer_namesake(groups, "властелин") == "властелин-колец"


def test_a_namesake_the_catalogue_knows_well_keeps_the_query() -> None:
    """🔴 «шерлок s3e2»: 27 раздач за именем - это не «каталог о нём не знает»."""
    groups = _groups({"шерлок": [20, 5, 2], "шерлок-холмс": [10] * 12})

    assert _richer_namesake(groups, "шерлок") is None


def test_more_pictures_but_fewer_releases_does_not_take_the_name() -> None:
    """🔴 «медведь s2e7»: у «Маша и Медведь» картин больше, а раздач вдвое меньше."""
    groups = _groups({"медведь": [10, 1, 1], "маша-и-медведь": [1] * 9})

    assert _richer_namesake(groups, "медведь") is None


def test_the_root_of_a_franchise_is_not_beaten_by_its_own_part() -> None:
    """🔴 «гарри поттер»: корень весит меньше части, но картин под ним больше."""
    groups = _groups({"гарри-поттер": [8, 3, 2, 1], "гарри-поттер-и-дары-смерти": [20, 17]})

    assert _richer_namesake(groups, "гарри-поттер") is None


def test_the_asked_word_must_stand_whole_not_inside_another_word() -> None:
    """🔴 «брат 2» уезжал в «Братья»: «брат» лежит там куском, а не словом."""
    groups = _groups({"брат": [1, 1], "братья": [5, 5, 5, 4]})

    assert _richer_namesake(groups, "брат") is None
    assert not _whole_word("братья", "брат")
    assert _whole_word("властелин-колец", "властелин")
    assert _whole_word("маша-и-медведь", "медведь")
    assert _whole_word("отец-мать-сестра-брат", "брат")


def test_a_third_name_of_a_barely_known_picture_yields_too() -> None:
    """🔴 Живой замер стенда: «стражи» стояли на «Часовых» (7 раздач) мимо 5 картин и 157."""
    groups = _groups({"часовые": [7], "стражи-галактики": [50, 40, 30, 20, 17]})

    assert _richer_namesake(groups, "стражи", "часовые") == "стражи-галактики"


def test_a_third_name_of_a_well_known_picture_keeps_the_query() -> None:
    """Псевдоним картины, за которой стоит каталог, запрос никому не отдаёт."""
    groups = _groups({"часовые": [9, 8], "стражи-галактики": [50, 40, 30, 20, 17]})

    assert _richer_namesake(groups, "стражи", "часовые") is None
