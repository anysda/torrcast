"""Зеркало обхода очереди отбора: годный релиз, а на осечке - строка и следующий."""

from __future__ import annotations

import time

import pytest

from tests.usecases.select_bench.world import GB, RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench.bench import Bench


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские строки обхода очереди отбора целиком."""


_ASKED = Args(query=["кино"])
_RUS = (AudioTrack(index=0, language="rus"),)


def _media(codec: str = "h264") -> Media:
    return Media(RUNTIME, _RUS, codec, height=1080, width=1920)


def test_the_first_fit_release_is_the_answer() -> None:
    """Счастливый путь: верх очереди годен, и дальше него отбор не идёт."""
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(2)]
    bench = Bench(Torrents(), prober=probes(pool, _media(), _media()))

    prep = bench.resolve(plan(pool), _ASKED, Said())

    assert prep.number == 1


def test_an_unfit_top_is_swapped_out_loud(capsys: pytest.CaptureFixture[str]) -> None:
    """Молчаливых подмен не бывает: каждая осечка стоит строки и следующего кандидата."""
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(2)]
    bench = Bench(Torrents(), prober=probes(pool, _media("av1"), _media()))

    prep = bench.resolve(plan(pool, recode_at=0.0), _ASKED, Said())

    assert prep.number == 2
    assert "релиз 1 не годится (av1) - беру 2" in capsys.readouterr().out


def test_a_queue_of_nothing_but_verdicts_ends_with_an_honest_refusal() -> None:
    """Все до одного прочитаны и осуждены - это отказ отбора, а не молчание роя."""
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(2)]
    bench = Bench(Torrents(), prober=probes(pool, _media("av1"), _media("vp9")))

    with pytest.raises(NotFoundError, match="годного релиза нет"):
        bench.resolve(plan(pool, recode_at=0.0), _ASKED, Said())


def test_a_queue_that_only_kept_silent_names_the_swarm_not_the_choice() -> None:
    """🔴 TC-435. Ни одного приговора - врать «годного релиза нет» тут нельзя."""
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(2)]
    dead = {f"hash-{one.magnet}" for one in pool}
    bench = Bench(Torrents(dead=dead), prober=probes(pool), meta_budget=0.5, probe_budget=0.5)

    with pytest.raises(NotFoundError, match="раздач в выдаче 2"):
        bench.resolve(plan(pool), _ASKED, Said())


def test_a_release_without_russian_waits_and_plays_when_nobody_has_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-178. Человек без картины не остаётся: гейт озвучки не слепой."""
    pool = [rel(name="r0 | Дубляж", seeders=100)]
    japanese = Media(
        RUNTIME, (AudioTrack(index=0, language="jpn"),), "h264", height=1080, width=1920
    )
    bench = Bench(Torrents(), prober=probes(pool, japanese))

    prep = bench.resolve(plan(pool), _ASKED, Said())

    assert prep.number == 1
    assert "русской озвучки нет ни в одной из проверенных раздач" in capsys.readouterr().out


@pytest.mark.machine
def test_the_hunt_for_a_russian_track_names_the_release_it_is_waiting_for() -> None:
    """Пока идёт спрос, бегущая строка называет, ЧЬЮ озвучку ищут: релиз N из M.

    Строка эта видна только на непрогретой раздаче: прогретая под меню отвечает
    мгновенно, и фазу спрашивать не у кого. Поэтому паспорт тут едет не сразу, а
    запасной - ещё и дольше верха: греется-то он с ним наперегонки.
    """
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(2)]
    read = probes(pool, _media("av1"), _media())
    said = Said()

    def slow(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        # Дольше шага опроса фазы (:meth:`Bench._wait`), иначе спрашивать нечего.
        time.sleep(0.3 if f"hash-{pool[0].magnet}/" in source_url else 0.9)
        return read(source_url, timeout=timeout, alive=alive)

    bench = Bench(Torrents(), prober=slow)

    prep = bench.resolve(plan(pool, recode_at=0.0), _ASKED, said)

    assert prep.number == 2, "верх осуждён по кодеку - спрашивали обоих"
    asked = {phase.rsplit(" - ", 1)[0] for phase in said.phases if phase.startswith("ищу русскую")}
    assert asked == {
        "ищу русскую озвучку: релиз 1 из 2",
        "ищу русскую озвучку: релиз 2 из 2",
    }


def test_a_walk_cut_by_the_budget_gets_no_spare_at_all(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-741. Запасной ход - ответ КОНЧИВШЕЙСЯ очереди, а не выход из срезанного обхода.

    Обход, вставший по цене приговоров, про непроверенный хвост очереди не знает ничего, и
    «русской нет ни у кого» тут было бы неправдой: ниже стоят нетронутые раздачи. Прежде
    такой обход отдавал зрителю английский звук первого же кандидата и называл это
    проверкой всей выдачи; теперь он называет нехватку своим именем и оставляет человеку
    ход - выбрать релиз руками.
    """
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(5)]
    english = Media(
        RUNTIME, (AudioTrack(index=0, language="eng"),), "h264", height=1080, width=1920
    )
    # Бюджет приговоров обнулён - каждый из них «дорогой», и обход встаёт на третьем.
    bench = Bench(Torrents(), prober=probes(pool, *[english] * 5), verdict_budget=0.0)

    with pytest.raises(NotFoundError) as refusal:
        bench.resolve(plan(pool), _ASKED, Said())

    said = str(refusal.value)
    printed = capsys.readouterr().out
    assert "русской озвучки нет ни в одной из проверенных раздач (3)" in said
    assert "выбери руками" in said, "очередь не кончилась - ход у человека есть"
    assert "включаю релиз" not in printed, "срезанный обход запасного хода не получает"


def test_the_hunt_for_a_track_nobody_has_stops_paying_and_plays_what_there_is(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-968. У поиска дорожки свой потолок, и кончается он тем же запасным ходом.

    Как только паспорт первой раздачи прямо назвал чужой язык, показывать зрителю уже есть
    что, и каждая следующая раздача спрашивается ровно об одном - нет ли дорожки у неё.
    Замер стенда на картине без русской озвучки вовсе: половина времени до картинки уходила
    на мёртвые рои, спрошенные только про звук, а кончалось это всё равно здесь.

    Бюджет поиска обнулён - значит после первого же отложенного платить нечем, и обход
    отдаёт отложенное, а не идёт по хвосту за ответом, который уже получил.
    """
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(5)]
    japanese = Media(
        RUNTIME, (AudioTrack(index=0, language="jpn"),), "h264", height=1080, width=1920
    )
    bench = Bench(Torrents(), prober=probes(pool, *[japanese] * 5), voice_budget=0.0)

    prep = bench.resolve(plan(pool), _ASKED, Said())

    assert prep.number == 1
    said = capsys.readouterr().out
    assert "русской озвучки нет ни в одной из проверенных раздач (1)" in said, said


def test_an_exhausted_queue_still_plays_the_named_foreign_track(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-178. Очередь кончилась - отказывать нечем: играет то, что есть, и вслух.

    Отрицательная половина предыдущей проверки: срезает обход именно потолок, а не сам
    нерусский звук. Спрошены все до последней раздачи - и решение остаётся за зрителем.
    """
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(3)]
    english = Media(
        RUNTIME, (AudioTrack(index=0, language="eng"),), "h264", height=1080, width=1920
    )
    bench = Bench(Torrents(), prober=probes(pool, *[english] * 3))

    prep = bench.resolve(plan(pool), _ASKED, Said())

    assert prep.number == 1
    assert (
        "русской озвучки нет ни в одной из проверенных раздач (3) - "
        "включаю релиз 1, звук английский" in capsys.readouterr().out
    )


def test_a_russian_track_lying_beside_the_video_saves_the_release(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-305. Русская дорожка отдельным файлом рядом с видео - это «озвучка есть».

    Живой класс: у аниме внутри видео только японский, а русский дубляж лежит в той же
    раздаче отдельным ``.mka``. Судить такой релиз по одному видеофайлу значит забраковать
    раздачу за то, чего в ней нет: очередь уходила к следующему релизу, хотя играть было
    чем - и играть верхом ранжира, а не тем, что осталось ниже.

    Опознаётся дорожка паспортом ВТОРОГО файла, а не именем: в аниме имя файла звука не
    называет язык никогда. Проверено откатом: верни гейту паспорт одного видеофайла - и
    отбор объявляет верх безрусским и берёт второй релиз.
    """
    pool = [rel(name="r0 | RUS(ext)", seeders=100), rel(name="r1 | Дубляж", seeders=90)]
    files = [
        TorrFile(0, "Erin - 01.mkv", 4 * GB),
        TorrFile(1, "Sound/Erin - 01.mka", 150 * 1024**2),
    ]
    japanese = Media(
        RUNTIME, (AudioTrack(index=0, language="jpn"),), "h264", height=1080, width=1920
    )
    russian = Media(RUNTIME, (AudioTrack(index=0, language="rus", title="Дубляж"),), None)
    inside = _media()

    def read(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        if f"hash-{pool[1].magnet}" in source_url:
            return inside
        return russian if source_url.endswith("/1") else japanese

    bench = Bench(Torrents(files=files), prober=read)

    prep = bench.resolve(plan(pool), _ASKED, Said())

    assert prep.number == 1, "релиз с русской дорожкой рядом с видео уступил место соседу"
    assert "без русской озвучки" not in capsys.readouterr().out
    assert prep.apart, "показ пойдёт японским: дорожка рядом с видео не опознана"
    assert prep.voice_file is not None and prep.voice_file.index == 1
    assert prep.voiced is russian, "дорожку выбирают у того файла, из которого её и возьмут"


def test_a_foreign_track_beside_the_video_saves_nobody() -> None:
    """Отдельный файл звука не русский - гейт остаётся на месте, а не «сойдёт»."""
    pool = [rel(name="r0 | RUS(ext)", seeders=100)]
    files = [
        TorrFile(0, "Erin - 01.mkv", 4 * GB),
        TorrFile(1, "Sound/Erin - 01.mka", 150 * 1024**2),
    ]
    japanese = Media(
        RUNTIME, (AudioTrack(index=0, language="jpn"),), "h264", height=1080, width=1920
    )
    english = Media(RUNTIME, (AudioTrack(index=0, language="eng"),), None)

    def read(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        return english if source_url.endswith("/1") else japanese

    bench = Bench(Torrents(files=files), prober=read)

    prep = bench.resolve(plan(pool), _ASKED, Said())

    assert not prep.apart, "чужая дорожка рядом с видео засчитана за русскую"
    assert prep.voiced is japanese


def test_a_nameless_track_beside_the_video_is_not_a_spare_way_either() -> None:
    """🔴 Безымянная дорожка рядом с видео запасным ходом гейта не становится."""
    pool = [rel(name="r0 | RUS(ext)", seeders=100)]
    files = [
        TorrFile(0, "Erin - 01.mkv", 4 * GB),
        TorrFile(1, "Sound/Erin - 01.mka", 150 * 1024**2),
    ]
    japanese = Media(
        RUNTIME, (AudioTrack(index=0, language="jpn"),), "h264", height=1080, width=1920
    )
    nameless = Media(RUNTIME, (AudioTrack(index=0),), None)

    def read(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        return nameless if source_url.endswith("/1") else japanese

    bench = Bench(Torrents(files=files), prober=read)

    assert not bench.resolve(plan(pool), _ASKED, Said()).apart


def test_a_video_without_any_sound_of_its_own_is_played_by_the_track_beside_it() -> None:
    """Исходник аниме: внутри видео звука нет вовсе, весь он лежит рядом отдельным файлом.

    Гейт озвучки такой паспорт не бракует - сказать о языке ему нечем, - и релиз доходил
    до показа немым. Проверено откатом: спрашивай второй файл только у паспорта с
    дорожками - и запись показа остаётся без единой.
    """
    pool = [rel(name="r0 | RAW", seeders=100)]
    files = [TorrFile(0, "Erin - 01.mkv", 4 * GB), TorrFile(1, "Erin - 01.mka", 150 * 1024**2)]
    mute = Media(RUNTIME, (), "h264", height=1080, width=1920)
    russian = Media(RUNTIME, (AudioTrack(index=0, language="rus", title="Дубляж"),), None)

    def read(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        return russian if source_url.endswith("/1") else mute

    prep = Bench(Torrents(files=files), prober=read).resolve(plan(pool), _ASKED, Said())

    assert prep.apart, "показ пойдёт немым: дорожки рядом с видео никто не спросил"
    assert prep.voiced is russian


class _Watched(Bench):
    """Стенд, который помнит ПОРЯДОК заведения прогревов: им и меряется ширина фронта."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.opened: list[int] = []

    def start(self, plan: Plan, number: int, patient: bool = False) -> _Prep:
        if (plan.picture.key, number) not in self.preps:
            self.opened.append(number)
        return super().start(plan, number, patient)


def test_a_fit_top_never_pays_for_a_third_release() -> None:
    """Счастливый путь греет двоих: третий ffprobe верх ранжира не оплачивает."""
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(5)]
    bench = _Watched(Torrents(), prober=probes(pool, *[_media()] * 5))

    bench.resolve(plan(pool), _ASKED, Said())

    assert bench.opened == [1, 2]


def test_a_queue_that_went_past_the_top_warms_two_at_once() -> None:
    """Верх осуждён - дальние кандидаты греются РАЗОМ, а не по одному за попытку."""
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(5)]
    bench = _Watched(Torrents(), prober=probes(pool, _media("av1"), *[_media()] * 4))

    prep = bench.resolve(plan(pool, recode_at=0.0), _ASKED, Said())

    assert prep.number == 2
    assert bench.opened == [1, 2, 3, 4]
