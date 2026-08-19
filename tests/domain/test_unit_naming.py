"""Зеркало :mod:`torrcast.domain.unit_naming`: как зовётся юнит показа и что в него едет.

Сторожится главное свойство списка: он полон. Каждая переменная, которая переопределяет
пути, обязана в нём быть - иначе заведомо тестовый показ уедет в боевые каталоги и начнёт
вытеснять оттуда чужое.
"""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.log_dir import LOG_ENV
from torrcast.adapters.filesystem.trace_journal.session_id import SID_ENV
from torrcast.domain.debug_handles import CTL_ENV, TRACE_ENV
from torrcast.domain.timeline_env import TIMELINE_ENV
from torrcast.domain.unit_naming import _PASS_ENV, _UNIT_NAME, _UNIT_TAG


def test_every_path_override_travels_into_the_unit() -> None:
    """Юнит обязан получить ВСЕ переопределения путей, а не часть из них.

    Забудь любое - и показ разъедется с командой, которая его запустила: конфиг возьмётся
    боевой, состояние чужое, прогрев уедет в боевое хранилище и станет вытеснять оттуда
    чужое по бюджету, а недельный след ляжет в другой каталог под другим id, и поиск с
    показом не склеятся в один сеанс.
    """
    for name in ("TORRCAST_CONFIG", "TORRCAST_STATE", "TORRCAST_WARM", LOG_ENV, SID_ENV):
        assert name in _PASS_ENV, name


def test_the_debug_handles_and_the_stopwatch_travel_along_with_the_paths() -> None:
    """Отладочные ручки включают то, что живёт в юните, поэтому едут туда же."""
    for name in (TRACE_ENV, CTL_ENV, TIMELINE_ENV):
        assert name in _PASS_ENV, name


def test_the_list_names_each_variable_exactly_once() -> None:
    """Повтор в списке - тихая примета того, что имя добавили дважды разными руками.

    Работать это не мешает, а вот читать список как договор мешает: непонятно, какая из
    двух строк тут настоящая и какую править.
    """
    assert len(_PASS_ENV) == len(set(_PASS_ENV))


def test_the_unit_name_is_something_systemd_can_actually_start() -> None:
    """Имя уезжает в ``systemd-run`` как есть, и негодное имя убивает показ целиком.

    Пробел, слеш или точка в имени - это уже не «некрасиво», а отказ запуска: показа не
    будет вовсе, а человек увидит ошибку системы вместо картины.
    """
    assert _UNIT_NAME
    assert not set(_UNIT_NAME) & set(" /.@\t")


def test_the_description_tag_is_a_prefix_that_can_be_stripped_off_the_key() -> None:
    """Описание юнита несёт ключ показа, и ``status`` достаёт его отрезанием метки.

    Опустей метка или слипнись она с ключом - ``status`` либо принял бы за ключ всё
    описание, либо не нашёл бы показ вовсе и сказал бы «ничего не играет» поверх идущей
    картины.
    """
    assert _UNIT_TAG
    assert _UNIT_TAG.endswith(" ")
    description = f"{_UNIT_TAG}moana-2"
    assert description.startswith(_UNIT_TAG)
    assert description[len(_UNIT_TAG) :] == "moana-2"
