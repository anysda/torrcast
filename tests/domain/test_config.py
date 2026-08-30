"""Зеркало :mod:`torrcast.domain.config`: настройки показа как готовое значение.

Сторожатся связи между умолчаниями, а не сами числа: пороги битрейта обязаны стоять
лестницей, ограничения с одним источником - иметь одно имя, хранилища памяти и диска -
оставаться разными, а послабление, снятое на приставке, не смеет двигать осторожное
умолчание.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from torrcast.domain.config import Config
from torrcast.domain.profile import ANDROID_TV, CAUTIOUS
from torrcast.domain.warm_settings import WARM_BUDGET, WARM_DIR


def test_the_bitrate_thresholds_stand_in_one_ladder_and_never_cross() -> None:
    """Четыре порога веса - это лестница, и порядок ступеней у неё один.

    Во что перекодируем - ниже планки, с которой перекодируем; та - не выше потолка
    отбора; выше потолка отбора релиз ещё берётся, но целиком перекодированным, и лишь
    выше последней ступени не берётся вовсе. Переставь любые две - и показ либо начнёт
    перекодировать в вес, который сам же считает тяжёлым, либо забракует то, что играет.
    """
    config = Config()

    assert config.recode_mbit < config.recode_at_mbit
    assert config.recode_at_mbit <= config.bitrate_warn_mbit
    assert config.bitrate_warn_mbit < config.bitrate_hard_mbit
    assert config.bitrate_hard_mbit < config.bitrate_recode_mbit


def test_the_segments_live_in_memory_and_the_warm_lives_on_a_disk() -> None:
    """Два хранилища и две разные природы: окно показа в памяти, целый фильм на диске.

    Сведи их в одно - и либо фильм не влезет в память, либо окно показа начнёт стучать по
    диску на каждом куске.
    """
    config = Config()

    assert PurePosixPath(config.hls_dir).is_relative_to("/dev/shm")
    assert not PurePosixPath(config.warm_dir).is_relative_to("/dev/shm")


def test_one_limit_has_one_name_and_the_config_only_repeats_it() -> None:
    """Бюджет и каталог прогретого приходят из своего модуля, а не заводятся тут заново.

    Разойдись эти два места - настройки обещали бы человеку один бюджет, а прогрев жил бы
    по другому, и вытеснение начиналось бы не там, где сказано.
    """
    config = Config()

    assert config.warm_dir == WARM_DIR
    assert config.warm_budget_gb == WARM_BUDGET / 1e9


def test_the_pack_rate_is_realtime_and_the_head_start_is_bought_by_the_burst() -> None:
    """Темп ровно реального времени, а запас впереди показа даёт разгон, а не темп.

    Единица БЕЗ разгона вредна дважды: первый сегмент готов не раньше своей длительности,
    а дальше приёмник идёт вровень с упаковкой и буферится на каждом стыке. Темп заметно
    выше единицы уводит упаковку вперёд без предела - на двухчасовом фильме это лишний час
    потока в памяти.
    """
    config = Config()

    assert config.hls_readrate == 1.0
    assert config.hls_burst > 0


def test_the_relaxation_measured_on_the_stick_never_moves_the_cautious_default() -> None:
    """Умолчания - осторожный профиль: незнакомый приёмник получает осторожный набор.

    У приставки потолок битрейта заметно выше, и это её замер. Утеки он в умолчание - и
    любой неизвестный телевизор получал бы смелые пороги, которых на нём никто не мерил.
    """
    config = Config()

    assert config.bitrate_warn_mbit == CAUTIOUS.warn_mbit
    assert config.recode_at_mbit == CAUTIOUS.recode_at_mbit
    assert config.hls_segment == CAUTIOUS.segment_seconds
    assert config.hls_burst == CAUTIOUS.burst
    assert ANDROID_TV.warn_mbit > config.bitrate_warn_mbit


def test_a_profile_is_chosen_by_the_device_passport_unless_a_human_named_one() -> None:
    """Пустое имя профиля - нормальный режим, а не недоделка настроек.

    Профиль выбирается сам, по паспорту устройства, и спрашивать об этом человека не надо.
    Поставь сюда непустое умолчание - и выбор по паспорту перестал бы работать у всех разом.
    """
    assert Config().receiver_profile == ""
    assert Config().hls_base_url == "", "адрес HLS тоже вычисляется сам, по маршруту до ТВ"


def test_an_unknown_key_in_a_saved_file_is_ignored_instead_of_crashing() -> None:
    """Конфиг переживает обновления инструмента и откаты назад.

    Упади чтение на незнакомом ключе - человек, откативший версию, остался бы вовсе без
    настроек вместо одного проигнорированного поля.
    """
    config = Config.from_json({"tv": "Гостиная", "ключ_из_будущего": True})

    assert config.tv == "Гостиная"
    assert config.receiver == Config().receiver


def test_an_unconfigured_install_already_recodes_and_already_warms() -> None:
    """Обе способности показа включены из коробки: настраивать их, чтобы работало, не надо.

    Перекод решает, что вообще можно смотреть: выключи его - и потолком отбора становится
    практический потолок приёмника, то есть тяжёлое просто перестаёт браться, а человек
    видит короткую очередь вместо живой. Прогрев решает, переживёт ли показ обрыв связи:
    выключи его - и показ снова живёт одним окном в памяти. Умолчание тут и есть прибор:
    свежая установка обязана и играть тяжёлое, и держать обрыв, ничего не спрашивая.
    """
    fresh = Config()

    assert fresh.recode, "без перекода потолком отбора становится потолок приёмника"
    assert fresh.warm, "без прогрева показ живёт только окном в памяти и не переживает обрыв"


def test_the_language_is_a_setting_of_the_product_and_english_out_of_the_box() -> None:
    """Язык живёт в настройке, а не в окружении: `LANG` тут не спрашивается вовсе."""
    assert Config().language == "en"
    assert Config.from_json({"tv": "Гостиная", "language": "ru"}).language == "ru"
