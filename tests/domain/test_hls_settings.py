"""Зеркало :mod:`torrcast.domain.hls_settings`: формат HLS, который берёт телевизор.

Числа этого модуля поставлены замерами на живом приёмнике, поэтому сторожат тут не сами
числа, а связи, из-за которых они такие: потолок веса куска обязан лежать НИЖЕ веса, на
котором показ умирал; служебные имена внутри каталога прогона не должны выглядеть
сегментами; допуски обязаны оставаться допусками, а не превращаться во второй порог.
"""

from __future__ import annotations

from torrcast.adapters.recode.recoder_settings import RUN_MAX
from torrcast.domain.hls_settings import (
    _SEGMENT_RE,
    AUDIO_BITRATE,
    AUDIO_CHANNELS,
    AUDIO_CODEC,
    AUDIO_PRIMING,
    HLS_SEGMENT_SECONDS,
    MAX_SEGMENT_BYTES,
    MIXED_PREFIX,
    MUTE_SECONDS,
    PACK_DIR,
    PACK_LIST,
    PACK_PENDING_BYTES,
    PACK_SHORT_SECONDS,
    PLAYING_FLAG,
    SHRINK_DIR,
    SPLIT_SLACK,
)
from torrcast.domain.profile import CAUTIOUS

#: Самый тяжёлый кусок, который живой приёмник ещё проиграл чисто.
LAST_CLEAN_BYTES = 18_700_000

#: Самый лёгкий кусок, на котором живой приёмник встал (потеря сессии, стоп на 8 с).
FIRST_DEADLY_BYTES = 19_400_000

#: Чем ffmpeg зовут «отдать дорожку как есть»: ровно это тут и запрещено.
PASSTHROUGH_CODECS = frozenset({"copy"})


def test_the_segment_cap_stays_under_the_weight_that_killed_the_show() -> None:
    """Потолок куска обязан лежать ниже замеренной смертельной границы, и с запасом.

    Замер на живом приёмнике: 18.7 МБ - чисто, 19.4 МБ - стоп. Правка, которая поднимет
    потолок в этот зазор или выше, вернёт ровно тот подвис, ради которого потолок и завели:
    приёмник выбрасывает буфер и перекачивает уже полученные куски.
    """
    assert MAX_SEGMENT_BYTES < LAST_CLEAN_BYTES
    assert MAX_SEGMENT_BYTES <= FIRST_DEADLY_BYTES * 0.85, "запас до смертельного веса < 15 %"


def test_the_receiver_measurements_are_the_profile_itself_and_not_a_second_copy() -> None:
    """Потолок веса и шаг сетки - свойства ПРИЁМНИКА и берутся из его профиля.

    Разойдись эти два места хоть на знак - показ пошёл бы по одному числу, а щупы и тесты
    мерили бы другое, и замер перестал бы что-либо значить.
    """
    assert CAUTIOUS.max_segment_bytes == MAX_SEGMENT_BYTES
    assert CAUTIOUS.segment_seconds == HLS_SEGMENT_SECONDS


def test_the_pending_budget_covers_the_pieces_a_healthy_run_legitimately_holds() -> None:
    """Порог несданного обязан отделять поломку от плотной работы, а не спорить с ней.

    Законно несданными бывают ровно два рода кусков: тот, что пишется прямо сейчас, и те,
    что придержаны под перекод (:data:`torrcast.adapters.recode.recoder_settings.RUN_MAX`). На
    потолке веса это ``(RUN_MAX + 1)`` кусков, и порог берётся вдвое сверх - иначе здоровый показ на
    тяжёлом кино объявлялся бы утечкой.
    """
    honest_peak = (RUN_MAX + 1) * MAX_SEGMENT_BYTES
    assert 2 * honest_peak <= PACK_PENDING_BYTES


def test_the_silence_deadline_outlives_two_honest_pieces_of_the_grid() -> None:
    """Обрыв связи объявляется позже, чем стоит честная выкладка двух кусков.

    Упаковка идёт в реальном времени, а кусок сетки по опорным кадрам бывает вдвое длиннее
    шага (остаток GOP). Опусти этот срок к длине куска - и обычная работа на длинном GOP
    читалась бы как «связи нет».
    """
    longest_piece = 2 * HLS_SEGMENT_SECONDS
    assert 2 * longest_piece <= MUTE_SECONDS


def test_the_tolerances_stay_tolerances_and_never_become_a_second_threshold() -> None:
    """Допуск короткого куска отделяет округление контейнера от настоящего обрыва.

    Замер: последний кусок фильма не дотягивает до обещанного на 0.000-0.065 с, а обрыв
    входа - на 0.6-10.0 с. Допуск обязан лежать между этими двумя мирами: ниже - честные
    концы фильмов пойдут в брак, выше - самый короткий обрыв станет невидимым.
    """
    assert 0.065 < PACK_SHORT_SECONDS < 0.6
    assert 0.0 < SPLIT_SLACK <= 1 / 24, "допуск границы - меньше кадра, а не целый кадр"
    assert SPLIT_SLACK * 100 < HLS_SEGMENT_SECONDS


def test_the_audio_priming_covers_the_measured_head_start_of_the_first_packet() -> None:
    """Первый пакет нашего AAC приходит ниже нуля на 0.021 с - лента обязана это покрыть.

    Недооценка возвращает дефект (муксер досдвинет первый кусок сам и только его),
    переоценка стоит миллисекунд начала - поэтому число берётся с запасом сверху, но
    остаётся на порядки меньше куска сетки.
    """
    assert AUDIO_PRIMING >= 0.021
    assert AUDIO_PRIMING < HLS_SEGMENT_SECONDS / 10


def test_nothing_service_shaped_inside_a_run_looks_like_a_ready_segment() -> None:
    """Каталог прогона перебирается глобом ``v*.ts``, и служебное туда попадать не смеет.

    Попади склейка, список ffmpeg или флажок картинки под этот перебор - показ счёл бы их
    готовыми кусками либо признаком «следующий открыт, прошлый дописан», и наружу уехало
    бы не то, что нарезали.
    """
    for name in (f"{MIXED_PREFIX}0.ts", PACK_LIST, PLAYING_FLAG):
        assert not name.startswith("v"), name
        assert _SEGMENT_RE.fullmatch(name) is None, name
    assert _SEGMENT_RE.fullmatch("v17.ts"), "настоящий сегмент обязан узнаваться"


def test_the_name_of_a_segment_carries_its_slot_as_a_number_and_nothing_else() -> None:
    """Имя куска несёт НОМЕР слота, и узнаётся кусок только вместе с ним.

    По этому имени показ и узнаёт слот (:func:`segment_slot` берёт группу и делает из неё
    число). Расширь узнавание до любого хвоста - и служебный файл вида ``vtmp.ts`` внутри
    каталога прогона сошёл бы за наш кусок, а попытка прочесть его слот кончилась бы не
    честным «имя не наше», а падением на разборе числа.
    """
    found = _SEGMENT_RE.fullmatch("v17.ts")
    assert found is not None
    assert int(found.group(1)) == 17, "из имени обязан доставаться сам номер слота"
    assert _SEGMENT_RE.fullmatch("vtmp.ts") is None, "без номера это не наш кусок"
    assert _SEGMENT_RE.fullmatch("v.ts") is None


def test_the_run_directories_never_collapse_into_one_another() -> None:
    """Каталог нарезки и каталог ужатия - РАЗНЫЕ места, и в этом весь смысл второго.

    Ужатие на месте заводит себе свой каталог ровно затем, чтобы не задеть рабочий каталог
    кодировщика. Слейся они в одно имя - одноразовый прогон вычищал бы куски, которые
    прямо сейчас нарезаются и вот-вот уедут на ТВ. То же и с остальными именами прогона:
    каждое названо своим делом, и совпадение любых двух - это молчаливая потеря одного
    из них.
    """
    names = [PACK_DIR, SHRINK_DIR, MIXED_PREFIX, PACK_LIST, PLAYING_FLAG]

    assert len(set(names)) == len(names), f"имена внутри прогона обязаны различаться: {names}"


def test_the_audio_is_always_recoded_and_never_passed_through() -> None:
    """Passthrough AC3/DTS запрещён: приёмник их не берёт, а ``copy`` пустил бы их как есть.

    Имя кодировщика тут и есть запрет: поставь сюда ``copy`` - и дорожка уехала бы на ТВ в
    исходном виде, то есть ровно тем, чего приёмник не декодирует.
    """
    assert AUDIO_CODEC not in PASSTHROUGH_CODECS
    assert AUDIO_CHANNELS == 2, "стерео: многоканальное приёмник сводить не обязан"


def test_the_audio_rate_is_a_rate_ffmpeg_understands_and_a_sliver_of_the_segment() -> None:
    """Битрейт звука назван так, как его читает ffmpeg, и весит малую долю куска.

    Вес куска - главный потолок показа: перевесь его звук, и на картинку осталось бы
    меньше, чем нарезано под неё, а потолок сегмента упирался бы в дорожку вместо видео.
    Звук у нас стерео и всегда перекодируется, то есть его вес мы назначаем сами.
    """
    assert AUDIO_BITRATE.endswith("k"), "ffmpeg читает ставку в своей k-нотации"
    kbit = int(AUDIO_BITRATE.removesuffix("k"))
    assert kbit > 0

    audio_bytes = kbit * 1000 / 8 * HLS_SEGMENT_SECONDS

    assert audio_bytes < MAX_SEGMENT_BYTES / 10, "звук - доля куска, а не его половина"
