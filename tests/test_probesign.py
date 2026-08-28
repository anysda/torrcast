"""Сторож подписи прибора: числа приёмника в дереве называют, чем они сняты.

Отрицательная проба тут главная: сторож обязан ловить снятую подпись, иначе он меряет
собственное молчание.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
PROFILES = (
    ROOT / "torrcast" / "domain" / "receiver_profile.py",
    ROOT / "torrcast" / "domain" / "android_tv_profile.py",
)


def tool(name: str) -> ModuleType:
    """Загрузить инструмент из ``scripts/``: пакетом каталог не является, путь известен."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_каждое_число_приёмника_назвало_свой_прибор() -> None:
    """🔴 TC-870: потолки приставки стояли в дереве без единой отметки о приборе.

    Порог тут ноль, и опустить его нечем: подпись ``НЕ НАЗВАН`` долг закрывает и остаётся
    греповой, а молчание от «снято щупом на приставке» не отличается ничем.
    """
    sign = tool("probesign")

    assert not [
        fault
        for profile in PROFILES
        for fault in sign.unsigned(profile.read_text(encoding="utf-8"))
    ]


def test_сторож_видит_поле_без_подписи() -> None:
    """Поле профиля без подписи названо поимённо, а не общим числом."""
    sign = tool("probesign")
    faults = sign.unsigned(
        "X = Profile(\n"
        "    key='k',\n"
        "    max_segment_bytes=1,  # снято: tvprobe · mpegts · TC-620\n"
        "    max_segment_seconds=2.0,\n"
        ")\n"
    )

    assert faults == ["X.max_segment_seconds: прибор замера не назван (нет «снято:»)"]


def test_сторож_не_берёт_подпись_соседа() -> None:
    """🔴 Подпись сверху приписала бы прибор чужому числу.

    В профиле приставки блок про нули сторожа (TC-728) стоит ровно НАД ``patience``, у
    которого замер другой: «подпись где-то рядом» тут значит неверную подпись.
    """
    sign = tool("probesign")
    faults = sign.unsigned(
        "X = Profile(\n"
        "    key='k',\n"
        "    # снято: tvprobe · mpegts · TC-620\n"
        "    patience=577.0,\n"
        ")\n"
    )

    assert faults == ["X.patience: прибор замера не назван (нет «снято:»)"]


def test_сторож_спрашивает_подпись_и_у_заявления_о_замере() -> None:
    """Заявление «тут не переопределено, и это замер» числа не имеет, а прибора требует."""
    sign = tool("probesign")
    body = (
        "X = Profile(\n    key='k',\n{block}    patience=1.0  # снято: tvprobe · fmp4 · TC-1\n)\n"
    )
    claim = "    # Нули сторожа тут не тронуты, и это замер, а не недосмотр.\n"

    assert sign.unsigned(body.format(block=claim)) == [
        "X, блок про замер со строки 3: прибор замера не назван (нет «снято:»)"
    ]
    assert not sign.unsigned(body.format(block=claim + "    # снято: tvprobe · fmp4 · TC-1\n"))
    assert not sign.unsigned(body.format(block="    # Тут просто пояснение без ссылки.\n"))


def test_сторож_не_верит_самоназванному_прибору() -> None:
    """Прибор и тракт берутся из закрытых списков: «глазами» прибором не считается."""
    sign = tool("probesign")
    faults = sign.unsigned("X = Profile(key='k', patience=1.0)  # снято: глазами · hls · TC-1\n")

    assert len(faults) == 2
    assert "прибор «глазами»" in faults[0]
    assert "тракт «hls»" in faults[1]


def test_сторож_не_принимает_отписку_вместо_места_замера() -> None:
    """Третье поле - карточка или дата, а не произвольное объяснение."""
    sign = tool("probesign")

    faults = sign.unsigned(
        "X = Profile(key='k', patience=1.0)  # снято: tvprobe · mpegts · замер вчера\n"
    )

    assert faults == [
        "X.patience: место замера «замер вчера» не карточка TC-<номер> и не дата ДД-ММ[-ГГГГ]"
    ]


def test_долг_неназванных_приборов_не_может_вырасти(tmp_path: Path) -> None:
    """Текущее число - потолок: ещё одна формальная подпись роняет команду."""
    sign = tool("probesign")
    profile = tmp_path / "profile.py"
    profile.write_text("# " + (sign.UNNAMED + " ") * (sign.UNNAMED_CEILING + 1), encoding="utf-8")

    assert sign.main([str(profile)]) == 1


def test_сторож_ходит_по_профилям_а_не_по_всякому_вызову() -> None:
    """Предмет назван: сборка профиля приёмника, а не любой вызов с доводами."""
    sign = tool("probesign")

    assert not sign.unsigned("X = Encode(preset='veryfast', mbit=9.0)\n")
