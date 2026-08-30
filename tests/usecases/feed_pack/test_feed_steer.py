"""Решение об упаковке: где ждать, где перепаковать и где честно сказать «не будет»."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tests.usecases.feed_pack.world import (
    FakeProc,
    factory,
    feed,
    grid,
    here,
    lay,
    packer,
    tract,
    vault,
)
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.feed_pack.feed_steer import IDLE_CIRCLES, _steer

if TYPE_CHECKING:
    from pathlib import Path

    from tests.fakes.journal import Tape
    from tests.usecases.feed_pack.world import FakeClock
    from torrcast.usecases.feed_pack.feed import Feed


def test_a_finished_show_is_never_diagnosed_again(tmp_path: Path) -> None:
    """Показ кончился - разбираться не с чем, а труп прогона не новость.

    Проверка стоит первой намеренно: на стыке серий сюда приходит приёмник с живого
    keep-alive прошлой серии и раньше получал «упаковка оборвалась» про наш же ffmpeg.
    """
    asked: list[int] = []
    show = feed(tmp_path)
    show.fatal = "показ окончен"

    assert _steer(show, 1, asked.append) is False and asked == []


def test_a_skipped_place_is_kept_silent_and_never_repacked(tmp_path: Path) -> None:
    """🔴 TC-501. Пропущенное место отвечается тишиной: 404 приёмник переживает хуже.

    И перепаковку такое ожидание не поднимает: тяжёлый кусок детерминирован, и второй
    прогон над ним получит ровно ту же копию.
    """
    asked: list[int] = []
    show = feed(tmp_path)
    show.skipped.add(4)

    assert _steer(show, 4, asked.append) is True and asked == []


def test_a_piece_finished_by_this_very_publish_is_not_a_seek_back(tmp_path: Path) -> None:
    """Кусок допаковался ровно этим publish - обычный ход показа, а не перемотка назад.

    Без этой проверки он был бы «ниже края, а файла нет»: замер - перезапуск на
    каждом четвёртом сегменте.
    """
    tract()
    asked: list[int] = []
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=0, out=show.out)
    lay(show.packer.run, 0)
    lay(show.packer.run, 1)

    assert _steer(show, 0, asked.append) is True
    assert asked == [] and (show.out / "v0.ts").exists()


def test_a_run_that_read_the_input_to_the_end_promises_nothing_beyond_its_edge(
    tmp_path: Path,
) -> None:
    """Упаковка честно дошла до конца входа - за краем файла не будет, и это не 404 зря."""
    tract()
    asked: list[int] = []
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=0, edge=2, out=show.out, proc=FakeProc(code=0))

    assert _steer(show, 5, asked.append) is False and asked == []


def test_the_wait_is_measured_in_seconds_of_film_and_not_in_segments(
    tmp_path: Path, journal: Path
) -> None:
    """«Вот-вот» - это про ВРЕМЯ: семь сегментов вперёд - это семьдесят секунд чтения.

    Замер на живом Q70D: перемотка +116 с внутри прогона стоила 57.8 с чёрного экрана,
    пока показ считал её обычным ходом.
    """
    fake = tract(now=100.0)
    asked: list[int] = []
    show = feed(tmp_path, grid=grid(600.0, 10.0), jump=15.0)
    show.packer = packer(
        tmp_path,
        first=0,
        edge=0,
        out=show.out,
        rate=1.0,
        burst=0.0,
        at=0.0,
        began=100.0,
        now=fake.monotonic,
    )

    # Планка чтения стоит на нуле фильма: сегмент 1 (10 с) достанут через 10 с - ждём.
    assert _steer(show, 1, asked.append) is True and asked == []
    # Сегмент 5 (50 с) - это пятьдесят секунд ожидания, дешевле перепаковать.
    fake.now = 100.0
    show.restarted = 0.0
    assert _steer(show, 5, asked.append) is True and asked == [5]


def test_neighbours_never_restart_the_packing_all_at_once(tmp_path: Path) -> None:
    """После перемотки приёмник просит куски пачкой: перезапустить обязан ровно первый."""
    fake = tract(now=100.0)
    asked: list[int] = []
    show = feed(tmp_path)

    assert _steer(show, 3, asked.append) is True and asked == [3]
    assert show.restarted == 100.0

    fake.now = 101.5
    assert _steer(show, 4, asked.append) is True and asked == [3], "сосед толкнул упаковку"

    fake.now = 103.0
    assert _steer(show, 4, asked.append) is True and asked == [3, 4]


def test_a_published_piece_means_the_source_reads_again(tmp_path: Path) -> None:
    """Прогон что-то выложил - значит сеть вернулась: признак обрыва снимается сам."""
    tract(now=500.0)
    asked: list[int] = []
    show = feed(tmp_path, vault=vault(tmp_path))
    show.offline = "источник молчит"
    show.moved = 0.0
    show.packer = packer(tmp_path, first=0, edge=0, out=show.out)
    lay(show.packer.run, 1)

    _steer(show, 9, asked.append)

    assert show.offline == "" and show.moved == 500.0


def test_a_silent_source_on_a_dead_network_is_not_pushed_every_two_seconds(tmp_path: Path) -> None:
    """Пока источник не читается, подъём ffmpeg стоит секунды и не даёт ничего: ждём дольше."""
    fake = tract(now=100.0)
    asked: list[int] = []
    show = feed(tmp_path, vault=vault(tmp_path))
    show.offline = "источник не читается"
    show.restarted = 97.0

    assert _steer(show, 1, asked.append) is True and asked == []

    fake.now = 103.0
    assert _steer(show, 1, asked.append) is True and asked == [1]


def test_a_source_that_reads_again_lifts_the_provisional_verdicts(tmp_path: Path) -> None:
    """🔴 TC-725. Прогон что-то выложил - значит и «ужать было неоткуда» больше не так.

    Приговор месту держится на том, что тяжёлый кусок детерминирован. У мёртвого
    источника этого свойства нет: он вернулся - и место снова обычное.
    """
    tract(now=500.0)
    show = feed(tmp_path, vault=vault(tmp_path))
    show.packer = packer(tmp_path, first=0, edge=0, out=show.out)
    lay(show.packer.run, 1)
    show.skipped = {4, 9, 12}
    show.doubted = {4, 12}

    _steer(show, 20, lambda _slot: None)

    assert show.skipped == {9}, "условный приговор пережил возврат источника"
    assert show.doubted == set()


def test_a_verdict_by_the_weight_of_the_piece_survives_the_source_coming_back(
    tmp_path: Path,
) -> None:
    """Кусок, который ужался и не влез, тем же и остаётся: перепаковка даст ровно то же."""
    tract(now=500.0)
    show = feed(tmp_path, vault=vault(tmp_path))
    show.packer = packer(tmp_path, first=0, edge=0, out=show.out)
    show.skipped = {4}

    _steer(show, 20, lambda _slot: None)

    assert show.skipped == {4}


def test_repacking_one_place_in_circles_ends_with_a_line_and_another_decision(
    tmp_path: Path,
) -> None:
    """Круг без прогресса детерминирован: следующий заход кончится ровно тем же.

    Замер живого показа на приставке: 45 и 65 таких кругов подряд по одному месту, семь
    минут без единого выложенного куска и без единой строки о том, что происходит.
    """
    fake = tract(now=100.0)
    asked: list[int] = []
    said: list[str] = []
    show = feed(tmp_path, log=said.append)

    for circle in range(IDLE_CIRCLES + 1):
        fake.now = 100.0 + circle * 3.0
        assert _steer(show, 3, asked.append) is True

    assert asked == [3] * IDLE_CIRCLES, "холостых кругов ровно столько, сколько терпим"
    assert 3 in show.skipped, "место, которого перепаковка не даёт, дальше живёт пропуском"
    want = phrase("feed.give_up", slot=3, circles=IDLE_CIRCLES)
    assert said == [want], "молчать об этом нельзя"

    fake.now = 200.0
    assert _steer(show, 3, asked.append) is True and asked == [3] * IDLE_CIRCLES


def test_a_place_that_was_given_out_starts_its_count_from_scratch(tmp_path: Path) -> None:
    """Круг считается по МЕСТУ и обнуляется выдачей: перемотка туда-обратно - не круг."""
    fake = tract(now=100.0)
    asked: list[int] = []
    show = feed(tmp_path)

    for circle in range(IDLE_CIRCLES - 1):
        fake.now = 100.0 + circle * 3.0
        _steer(show, 3, asked.append)
    fake.now = 130.0
    _steer(show, 4, asked.append)  # соседнее место - это работа, а не круг

    assert show.circling == (4, 1)
    for circle in range(IDLE_CIRCLES - 1):
        fake.now = 140.0 + circle * 3.0
        _steer(show, 3, asked.append)

    assert 3 not in show.skipped, "счёт по чужому месту приговора не выносит"


def _seek_stand(tmp_path: Path) -> tuple[Feed, FakeClock]:
    """Лента, у которой настоящий заход упаковки: подделан медиатракт, но не решение.

    Заходы считаются строкой журнала «заход упаковки», и пишет её сам заход
    (:func:`torrcast.usecases.feed_pack.feed_restart._restart`), - поэтому подделывать
    перезапуск доводом тут нельзя: считать было бы нечего.
    """

    def _start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Any:
        run.mkdir(parents=True, exist_ok=True)
        return packer(out.parent, out=out, run=run, first=first)

    clock = tract(
        now=1000.0,
        spawn=here,
        settle_start=lambda source, at, *rest: (at, at),
        pack_command=lambda *a, **k: ["ffmpeg"],
        packer=factory(_start),
    )
    show = feed(tmp_path, grid=grid(7800.0, 10.0))
    show.packer = packer(tmp_path, first=0, edge=4, out=show.out)
    return show, clock


def test_a_seek_inside_the_film_leaves_the_pack_a_single_owner(tmp_path: Path, tape: Tape) -> None:
    """🔴 TC-634. После перемотки заходы упаковки идут только на слот цели.

    Мерка тут - ЧИСЛО и СЛОТЫ заходов, а не «жив ли показ»: живой показ бывает зелёным и
    на сломанном дереве. Живой замер 17-08 (перемотка 32.3 → 900): 28 заходов за прогон,
    попеременно слот 85 (цель, 936.2 с) и слот 5 (место, откуда зритель ушёл, 50.9 с), ни
    один не дошёл до плёнки, показ дважды сказал `dark` и не поднялся.

    Ждущий запрос старого места возвращается в это решение каждые 0.2 с все ``wait``
    секунд, поэтому одного оставленного GET хватает, чтобы уводить упаковку от зрителя
    вечно: держала его только защёлка по времени, а спор шёл о МЕСТЕ.
    """
    show, clock = _seek_stand(tmp_path)
    show.prune(900.0)  # круг часов показа: зритель смотал на 900-ю секунду

    for _ in range(4):
        show.segment(85)  # приёмник просит цель перемотки
        clock.now += 3.0  # защёлка «не толкаемся» отпустила: она короче захода упаковки
        show.segment(5)  # ...а оставленный запрос старого места всё ещё ждёт своего файла
        clock.now += 3.0

    slots = [told["слот"] for told in tape.named("заход упаковки")]
    assert slots == [85], f"у упаковки больше одного хозяина: заходы {slots}"


def test_a_place_left_behind_is_kept_silent_instead_of_repacking_the_show(
    tmp_path: Path, tape: Tape
) -> None:
    """Отступившее место отвечается тишиной и говорит об этом строкой, а не молчит совсем.

    Ответ тот же, что у честно пропущенного места: 404 приёмник переживает хуже тишины, а
    круг перепаковки под это место увёл бы упаковку от зрителя. Строка нужна, чтобы
    отступление было видно в ленте: «заходов нет» и «показ умер» иначе неразличимы.
    """
    show, clock = _seek_stand(tmp_path)
    show.prune(900.0)
    show.segment(85)  # упаковка ушла на цель перемотки
    clock.now += 3.0

    assert show._steer(5) is True, "отступившее место обязано ЖДАТЬ, а не получать 404"

    assert tape.named("место позади зрителя") == [{"слот": 5, "зритель": 900.0}]
    assert [told["слот"] for told in tape.named("заход упаковки")] == [85]
    assert show.skipped == set(), "место, на которое зритель ещё вернётся, не приговаривают"


def test_a_real_seek_back_still_repacks_once_the_show_clock_has_caught_up(
    tmp_path: Path, tape: Tape
) -> None:
    """Отступление старого места не запирает честную перемотку назад.

    Зритель, ушедший вглубь, двигает за собой и границу выметенного. Первый запрос после
    перемотки застаёт ещё старое место зрителя и ждёт файла, а следующий круг часов показа
    называет новое - и поток перепаковывается обычным ходом. Цена честной перемотки назад
    тут - один круг опроса приёмника, а не показ.
    """
    show, clock = _seek_stand(tmp_path)
    show.prune(900.0)
    show.segment(85)
    clock.now += 3.0

    show.segment(5)  # зритель смотал назад, часы показа об этом ещё не знают
    show.prune(50.0)  # ...круг часов - и знают
    clock.now += 3.0
    show.segment(5)

    slots = [told["слот"] for told in tape.named("заход упаковки")]
    assert slots == [85, 5], f"честная перемотка назад не перепаковала поток: заходы {slots}"
