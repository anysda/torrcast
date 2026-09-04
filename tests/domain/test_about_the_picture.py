"""Зеркало :mod:`torrcast.domain.about_the_picture`: имя работы О картине, а не картины."""

from torrcast.domain.about_the_picture import _about_the_picture


def test_the_tails_of_a_work_about_the_picture_are_known_by_name() -> None:
    """Список тот же, ради которого закрыт `_EDITION_TAILS`: за этими хвостами стоит
    другая работа с другим хронометражом."""
    assert _about_the_picture("Евангелион Нового Поколения: дополнительные материалы")
    assert _about_the_picture("Евангелион - дополнение")
    assert _about_the_picture("Властелин колец - история создания")
    assert _about_the_picture("Твин Пикс: Огонь, иди со мной - Пропавшие фрагменты")
    assert _about_the_picture("Властелин Колец. Презентация с Каннского фестиваля")


def test_the_picture_itself_is_not_a_work_about_it() -> None:
    """🔴 «Расширенная версия» сюда не входит: список закрыт, и лишнее слово в нём
    разводило бы по двум пунктам одну картину, а не берегло бы две."""
    assert not _about_the_picture("Евангелион")
    assert not _about_the_picture("Наруто: Ураганные хроники")
    assert not _about_the_picture("Нечто. Расширенная версия")
    assert not _about_the_picture("Врата Штейна: Полное издание")
