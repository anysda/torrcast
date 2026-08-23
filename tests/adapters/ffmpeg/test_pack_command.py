"""Проверяет сборку команды упаковки без запуска ffmpeg."""

from dataclasses import dataclass
from typing import Any

from torrcast.adapters.ffmpeg.pack_command import pack_command
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install


@dataclass
class _Grid:
    bounds: tuple[float, ...] = (0.0, 10.0, 20.0)
    count: int = 3
    origin: float = 1.4
    on_keys: bool = True

    def start(self, slot: int) -> float:
        return self.bounds[slot]

    def end(self, slot: int) -> float:
        return self.bounds[slot + 1] if slot + 1 < self.count else 30.0


class _Spy(Silent):
    """Молчащая лента, которая запоминает отметки: сборка обязана оставлять след."""

    def __init__(self) -> None:
        self.marks: list[tuple[str, dict[str, Any]]] = []

    def mark(self, name: str, **facts: Any) -> None:
        self.marks.append((name, facts))


def _cuts(command: list[str]) -> list[float]:
    """Резы из собранной команды; ключа нет — резов нет."""
    if "-segment_times" not in command:
        return []
    return [float(part) for part in command[command.index("-segment_times") + 1].split(",")]


def test_a_mark_later_than_its_boundary_never_becomes_a_cut_in_the_past() -> None:
    """🔴 TC-629. Отрицательный рез наружу не выходит, откуда бы ``at`` ни пришёл.

    Резы отмеряются от первого пакета прогона, поэтому рез «раньше начала» — место,
    которого нет: сегментный муксер на таком списке не режет вовсе и пишет один кусок до
    конца фильма. Живая приёмка TC-617 поймала ровно это — 240 МБ при норме 12 МБ.
    """
    command = pack_command("http://source", 2, "/run/", _Grid(), 1, 25.0)
    assert _cuts(command), "резы обязаны остаться: без них муксер пишет один кусок до конца"
    assert min(_cuts(command)) > 0.0, "рез раньше начала прогона муксеру не выразить"


def test_the_last_resort_clamp_shouts_into_the_journal_instead_of_replacing_a_number() -> None:
    """🔴 TC-629. Зажим — заявка на разбор, а не тихая подмена измеренного места.

    Встать позже своей границы прогон умеет по-честному: у mpegts перемотка садится на
    СЛЕДУЮЩИЙ опорный кадр. Такой уезд в сегмент укладывается и до зажима не доходит, но
    если он сюда всё же придёт, зажим положит куски под именами мест, в которых поток не
    начинался. Молчать об этом нельзя: тихая подмена и довела дефект живым до приёмки.
    """
    spy = _Spy()
    install(spy)
    pack_command("http://source", 2, "/run/", _Grid(), 1, 25.0)
    said = [facts for name, facts in spy.marks if name == "заход позже своей границы"]
    assert said, "зажим смолчал: разбирать потом будет нечего"
    assert said[0]["граница"] == 10.0
    assert said[0]["замер"] == 25.0


def test_a_uniform_grid_lands_late_by_construction_and_is_not_called_an_incident() -> None:
    """🔴 TC-693. На ровной сетке посадка позже границы - норма пути, а не авария.

    Граница ровной сетки с опорным кадром не совпадает по построению, и перемотка mpegts
    садится на следующий кадр: замер даёт 688 таких границ из 768, тогда как на сетке по
    опорным кадрам - 0 из 419. Аварийное имя тут красило бы штатную работу, поэтому
    запись своя и спокойная, а само число зажимается ровно так же.
    """
    spy = _Spy()
    install(spy)
    pack_command("http://source", 2, "/run/", _Grid(on_keys=False), 1, 25.0)
    names = [name for name, _ in spy.marks]
    assert "заход позже своей границы" not in names, "штатная посадка названа аварией"
    said = [facts for name, facts in spy.marks if name == "посадка позже границы на ровной сетке"]
    assert said and said[0]["граница"] == 10.0, "зажим смолчал: разбирать потом будет нечего"


def test_a_run_standing_on_its_boundary_is_not_reported_as_an_incident() -> None:
    """Штатный заход следа не пачкает: заявка на разбор — только настоящий уезд."""
    spy = _Spy()
    install(spy)
    pack_command("http://source", 2, "/run/", _Grid(), 1, 9.5)
    assert not [name for name, _ in spy.marks if name == "заход позже своей границы"]


def test_a_mark_before_its_boundary_still_keeps_its_run_up_lead_in() -> None:
    """Последний рубеж не трогает штатный заход: докатка остаётся отдельным резом."""
    command = pack_command("http://source", 2, "/run/", _Grid(), 1, 9.5)
    assert _cuts(command)[0] == 0.5
    assert command[command.index("-segment_start_number") + 1] == "0"


def test_builds_segment_command_from_supplied_grid() -> None:
    command = pack_command("http://source", 2, "/run/", _Grid(), 1, 9.5, burst=30.0)
    assert command[:3] == ["ffmpeg", "-hide_banner", "-loglevel"]
    assert command[command.index("-map") + 1] == "0:v:0"
    assert "0:a:2" in command
    assert command[-1] == "/run/v%d.ts"
    assert "-output_ts_offset" in command
    assert any("10.500" in argument for argument in command)


def test_a_run_into_the_last_slot_alone_still_names_its_cut() -> None:
    """🔴 TC-771. Молчание про резы сегментный муксер читает как «режь своим умолчанием».

    Заход в один-единственный слот-хвост - штатная работа прогрева: заход, доведённый не
    до конца, оставляет слоты, которые потом переделываются поодиночке. Границ сетки
    внутри такого захода нет, и список резов выходил пустым; муксер брал своё умолчание
    (2 с) и закрывал хвост на первом опорном кадре за ним. Замер настоящим ffmpeg: вместо
    7.884 с / 2 086 048 Б наружу шёл кусок 2.113 с / 554 788 Б, то есть конец фильма.

    Поэтому рез называется всегда, а стоит он там же, куда смотрит ``-to``: за концом
    прогона, где муксеру его уже не достать.
    """
    grid = _Grid()
    at = grid.start(2)
    command = pack_command("http://source", 2, "/run/", grid, 2, at, until=2)
    stop = float(command[command.index("-to") + 1])

    assert _cuts(command), "без резов муксер режет по своему умолчанию и рвёт хвост пополам"
    assert min(_cuts(command)) >= stop - at, "названный рез стоит внутри захода"
    assert command[command.index("-segment_start_number") + 1] == "2", "имя куска съехало"


def test_a_live_run_restarted_on_the_last_slot_names_its_cut_too() -> None:
    """Тот же слот-хвост без предела захода: живой упаковке умолчание муксера так же
    разрезало бы хвост, а её кусок уезжает приёмнику прямо сейчас.
    """
    grid = _Grid()
    at = grid.start(2)
    command = pack_command("http://source", 2, "/run/", grid, 2, at)

    assert _cuts(command) and min(_cuts(command)) > grid.end(2) - at, (
        "рез внутри захода: хвост уедет обрезанным"
    )
