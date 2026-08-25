"""Зеркало признака «зритель закрыл показ с пульта»: что осталось на экране вместо показа."""

from __future__ import annotations

from tests.adapters.chromecast.cast.wired import Device, Wired
from torrcast.adapters.chromecast.cast.viewer_closed import _viewer_closed


def test_our_own_application_on_the_screen_is_not_a_closed_show() -> None:
    """Приложение на экране наше - показ никто не закрывал."""
    assert _viewer_closed(Wired()) is False


def test_an_empty_screen_is_the_hand_of_the_viewer() -> None:
    """Приложение убрано с экрана целиком - так выглядит закрытый с пульта показ.

    Сеанс 11-08-2026: статус ушёл в ``UNKNOWN``, приложение пропало из статуса вовсе -
    в отличие от четырёх смертей того же вечера, где приходил ``IDLE``/``ERROR``, а
    приложение оставалось на экране.
    """
    assert _viewer_closed(Wired(Device(app=""))) is True


def test_the_receivers_backdrop_is_an_empty_screen_too() -> None:
    """Заставка приёмника - тот же пустой экран: показа на нём нет."""
    receiver = Wired(Device(app=Wired.BACKDROP_APP))

    assert _viewer_closed(receiver) is True


def test_someone_elses_application_is_someone_elses_show() -> None:
    """Чужое приложение - это чужой показ, а не воля зрителя закрыть наш."""
    assert _viewer_closed(Wired(Device(app="CHUJOI"))) is False


def test_the_screen_we_cleared_ourselves_is_not_the_viewers_will() -> None:
    """Перед каждым повтором LOAD экран чистим мы сами, и это не закрытие показа.

    Считать своё же закрытие волей зрителя значит хоронить показ ровно там, где его
    надо поднимать: неудавшийся повтор LOAD оставляет экран пустым.
    """
    receiver = Wired(Device(app=""))
    receiver._restart_app()
    receiver._device()  # соединение поднимает следующий же LOAD - и экран всё ещё пуст

    assert _viewer_closed(receiver) is False


def test_a_successful_load_clears_our_own_mark() -> None:
    """Наше приложение снова на экране - отметка о своём закрытии гаснет.

    Иначе первый же повтор LOAD за сеанс выдал бы показу вечную индульгенцию, и
    закрытый с пульта показ после него воскрешался бы как ни в чём не бывало.
    """
    receiver = Wired(Device(app=""))
    receiver._restart_app()
    receiver._device()
    receiver.device.status.app_id = Wired.MEDIA_APP  # LOAD взят, приложение снова наше

    assert _viewer_closed(receiver) is False, "приложение наше - показ идёт"

    receiver.device.status.app_id = ""

    assert _viewer_closed(receiver) is True, "экран опустел уже не нашей рукой"


def test_without_a_connection_there_is_nothing_to_judge_by() -> None:
    """Соединения нет вовсе - о том, что на экране, судить нечем."""
    receiver = Wired()
    receiver._cast = None

    assert _viewer_closed(receiver) is False
