"""Композиционный корень: после сборки след пишет настоящая лента, а не молчание."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.runtime.slot_contract import slots
from torrcast.adapters.console.console.progress import Progress
from torrcast.adapters.filesystem.state.file_state_store import FileStateStore
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.trace_journal.file_journal import FileJournal
from torrcast.adapters.health.system_health_environment import SystemHealthEnvironment
from torrcast.adapters.systemd.transient_show_unit import TransientShowUnit
from torrcast.adapters.warm_environment import environment as warm_environment
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install, journal
from torrcast.ports.progress.slot import factory as progress_factory
from torrcast.ports.show_unit.slot import unit
from torrcast.ports.state_store.slot import store
from torrcast.runtime.wire import wire
from torrcast.usecases import doctor_command as _doctor_command
from torrcast.usecases import doctor_environment as _doctor_environment
from torrcast.usecases.warm import _state as _warm_state


def test_wiring_puts_the_real_journal_on_the_port() -> None:
    """До сборки след молчит, после - пишет; это и есть работа корня."""
    install(Silent())
    assert isinstance(journal(), Silent)

    wire()

    assert isinstance(journal(), FileJournal)


def test_wiring_puts_the_real_ports_and_environments() -> None:
    """Каждый слот корня занят ТЕМ САМЫМ адаптером, а не однофамильцем той же арности.

    Живое приложение собирается на запуске (``tests.conftest._wired``), поэтому
    повторный вызов тут только подтверждает: слот берёт своё значение отсюда.

    🔴 Сверяется САМО значение, а не то, что его можно позвать: пустышка нужной арности
    договору порта отвечает не хуже настоящего адаптера. Порты, читаемые через доступ
    слота (``store()``, ``unit()``), сверяются точным классом: корень кладёт свежий
    экземпляр, и тождества у него быть не может.

    Полноту этого списка держит не память, а сторож гейта (``scripts/test-gate``): он
    сам сличает доводы, которые кладёт :func:`wire`, с тем, что сверяет зеркало, и
    новый слот без сверки по значению не пропустит.
    """
    wire()

    # Порты процесса: ход работы, состояние и юнит показа.
    assert progress_factory() is Progress
    assert type(store()) is FileStateStore
    assert type(unit()) is TransientShowUnit

    # Среда прогрева и её разбор по слотам ленты прогрева.
    assert _warm_state._environment is warm_environment
    assert _warm_state.segment_name is warm_environment.segment_name
    assert _warm_state.segment_slot is warm_environment.segment_slot
    assert _warm_state._hms is warm_environment.hms
    assert _warm_state.Packer is warm_environment.packer_type
    assert _warm_state.ffmpeg_pack_command is warm_environment.pack_command
    assert _warm_state.settle_start is warm_environment.settle_start
    assert _warm_state.spot_out is warm_environment.spot_out
    assert _warm_state.AUDIO_MBIT is warm_environment.audio_mbit
    assert _warm_state.TS_OVERHEAD is warm_environment.ts_overhead

    # Самопроверка окружения: системная среда проб и чтение настроек командой.
    assert type(_doctor_environment.environment) is SystemHealthEnvironment
    assert _doctor_command._settings is load_config


#: Вопрос задаётся СВЕЖЕМУ процессу и по одному модулю за раз, потому что оба соседа
#: покупают ответ. Общий прогон покупает его чужим импортом: сосед по набору втянул
#: совместимый фасад, и тот раздал среду побочным эффектом. Обход всего дерева в одном
#: процессе покупал его сам у себя: `torrcast/choice.py` импортировался раньше
#: `torrcast/usecases/choice.py` просто по алфавиту - и к моменту вопроса среда уже стояла.
#: Спрашивать надо ровно одно: раздал ли КОРЕНЬ, а не подвернулся ли импорт.
#: Сверщик договоров (`tests.runtime.slot_contract`) продукта не импортирует вовсе,
#: поэтому его собственный импорт ответа не покупает.
_SLOTS_AFTER_WIRING = """
import importlib, sys

from torrcast.runtime.wire import wire
from tests.runtime.slot_contract import unfit

wire()

for line in unfit(importlib.import_module(sys.argv[1])):
    print(line)
"""


def _modules_with_slots(root: Path) -> list[str]:
    """Модули, где объявлено имя без значения: «сюда положит корень»."""
    found = []
    for path in sorted((root / "torrcast").rglob("*.py")):
        if path.name != "__init__.py" and slots(path.read_text(encoding="utf-8")):
            found.append(".".join(path.relative_to(root).with_suffix("").parts))
    return found


@pytest.mark.machine
def test_no_scenario_is_left_without_its_environment() -> None:
    """После сборки каждый слот занят, и занят по своему договору - у КАЖДОГО модуля.

    Сценариям, которым внешний мир приходит мешком-средой, её раздавал импорт
    совместимого фасада. Фасад прогрева не импортирует никто - и живой каст падал
    ``NameError: _environment`` уже после того, как первые куски уехали на телевизор,
    при том что весь сухой набор был зелёным: в общем прогоне среду успевал раздать
    сосед по набору. Голое объявление без значения - это и есть «сюда положит корень»,
    поэтому мера ровно такая: чем корень собранного приложения эти имена заполнил.

    Заполнил - половина ответа. Вторая половина в том, ЧЕМ: имя договора стоит рядом с
    объявлением, и перепутанный слот отличается от забытого только тем, что падает
    позже - на вызове, а не на чтении. Поэтому мера сверяет положенное с договором -
    зов у зова, метод у порта, - а не наличие атрибута.

    ⚠️ Прошлая редакция этой меры спрашивала не то и потому пропустила ровно ту же
    беду у выбора раздачи (TC-630): она делала ``import torrcast.cli`` «как точка входа»,
    а тот тянул фасад, который среду и раздавал. Мера ответа не покупает: корень
    зовётся в одиночку, каждый модуль спрашивается своим процессом.

    Исключений у меры больше нет: последним связыванием вне корня оставался добор
    кандидатов, и оно переехало сюда вместе со сносом фасада ``torrcast.reinforce``.
    """
    root = Path(__file__).resolve().parents[2]
    broken = []
    for name in _modules_with_slots(root):
        done = subprocess.run(
            [sys.executable, "-c", _SLOTS_AFTER_WIRING, name],
            capture_output=True,
            text=True,
            check=False,
            cwd=root,
        )
        assert done.returncode == 0, f"{name}: {done.stderr}"
        broken += done.stdout.splitlines()
    assert broken == [], "корень собрал внешний мир не по договору:\n" + "\n".join(broken)
