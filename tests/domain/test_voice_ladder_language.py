"""Лестница озвучек идёт за языком продукта; русская сторона при этом не двигается."""

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.catalogs.tongue import EN, RU, _choose_tongue
from torrcast.domain.media import Media
from torrcast.domain.voice_order import voice_order

#: Живой набор дорожек японского аниме: оригинал, русский дубляж, английский дубляж и
#: служебная дорожка комментариев. Номера в файле нарочно НЕ совпадают с ожидаемым
#: порядком ни на одной из лестниц - иначе проверка сошлась бы и на порядке дорожек.
ANIME = (
    AudioTrack(index=0, language="jpn", title="Original"),
    AudioTrack(index=1, language="rus", title="Дубляж"),
    AudioTrack(index=2, language="eng", title="Dub"),
    AudioTrack(index=3, language="rus", title="Комментарии режиссёра"),
)


def ladder(tracks: tuple[AudioTrack, ...], language: str, native: bool = False) -> list[int]:
    """Весь порядок дорожек целиком, а не один победитель: сдвиг в середине тоже сдвиг."""
    order = sorted(tracks, key=lambda track: voice_order(track, native, language))
    return [track.index for track in order]


def test_the_russian_ladder_survives_the_english_one_word_for_word() -> None:
    """🔴 Русскоязычный продукт обязан играть по-русски: под ``--ru`` русский дубляж
    наверху, а дальше - английская дорожка, оригинал и служебная, в этом порядке.

    Сторож поставлен против ровно одной беды - подъёма английского звука БЕЗ учёта языка
    продукта. Отрицательная проба к нему такая: сделать ярус безусловным
    (:func:`~torrcast.domain.voice_order._tier` без проверки языка) - и русский дубляж
    уедет со своего первого места под английский, а проверка покраснеет.
    """
    assert ladder(ANIME, RU) == [1, 2, 0, 3]


def test_the_english_voice_is_the_first_fallback_of_the_russian_ladder() -> None:
    """🔴 Под ``--ru`` нет русской - включай английскую: она выше оригинала, а не ниже.

    До этой ступени английский дубляж не отличался от любого чужого и лежал НИЖЕ
    оригинала. Отрицательная проба: снять ступень
    (:data:`~torrcast.domain.audio_track.STEP_ENGLISH` в
    :func:`~torrcast.domain.voice_order.voice_order`) - и на этом наборе без русской
    дорожки выбор возвращается на японский оригинал.
    """
    assert ladder(ANIME[:1] + ANIME[2:], RU) == [2, 0, 3]


def test_the_original_beats_any_other_foreign_voice_but_not_the_english_one() -> None:
    """Лестница целиком: английская → оригинал → все остальные, служебные - в самом низу.

    Дорожки живые («Тачки 3», WEB-DL 1080p, и английский комментарий из того же набора),
    русские из набора убраны.
    """
    tracks = (
        AudioTrack(index=0, language="ukr", title="Дубляж"),
        AudioTrack(index=1, language="eng", title="Оригинал"),
        AudioTrack(index=2, language="kaz", title="Дубляж"),
        AudioTrack(index=3, language="eng", title="Director commentary"),
    )

    assert ladder(tracks, RU) == [1, 0, 2, 3]


def test_the_original_wins_only_when_there_is_neither_russian_nor_english() -> None:
    """Нет ни русской, ни английской - играет оригинал, а не чужой дубляж."""
    tracks = (
        AudioTrack(index=0, language="jpn", title="Original"),
        AudioTrack(index=1, language="ukr", title="Дубляж"),
    )

    assert ladder(tracks, RU) == [0, 1]


def test_the_russian_ladder_of_a_native_picture_survives_it_too() -> None:
    """Отечественная картина: её собственная дорожка остаётся лучшей под русской ручкой."""
    tracks = (
        AudioTrack(index=0, language="rus", title="[DUB] DVD-R5 AMALGAMA"),
        AudioTrack(index=1, language="rus"),
        AudioTrack(index=2, language="eng", title="Dub"),
    )

    assert ladder(tracks, RU, native=True) == [1, 0, 2]


def test_an_english_dub_beats_the_original_of_a_japanese_cartoon() -> None:
    """Под ``--en`` английский дубляж выше японского оригинала, а русский - ниже обоих."""
    assert ladder(ANIME, EN) == [2, 0, 1, 3]


def test_an_english_picture_plays_english_and_not_its_russian_dub() -> None:
    """Англоязычная картина под ``--en``: свой звук наверху, дубляжи - под ним."""
    tracks = (
        AudioTrack(index=0, language="rus", title="Дубляж"),
        AudioTrack(index=1, language="eng", title="Original"),
    )

    assert ladder(tracks, EN) == [1, 0]


def test_english_stays_on_top_of_a_native_picture_as_well() -> None:
    """Английский наверху ВСЕГДА: происхождение картины английскую ручку не отменяет."""
    tracks = (
        AudioTrack(index=0, language="rus"),
        AudioTrack(index=1, language="eng", title="Dub"),
    )

    assert ladder(tracks, EN, native=True) == [1, 0]


def test_the_english_original_comes_before_the_english_dub() -> None:
    """Внутри английского яруса ступень решает по-прежнему: оригинал впереди дубляжа."""
    tracks = (
        AudioTrack(index=0, language="eng", title="Dub"),
        AudioTrack(index=1, language="eng", title="Original"),
    )

    assert ladder(tracks, EN) == [1, 0]


def test_a_service_track_stays_at_the_very_bottom_of_the_english_ladder() -> None:
    """Английский комментарий съёмочной группы - тоже английский, но слушать хотели фильм."""
    tracks = (
        AudioTrack(index=0, language="eng", title="Director commentary"),
        AudioTrack(index=1, language="jpn", title="Original"),
    )

    assert ladder(tracks, EN) == [1, 0]


def test_an_untagged_english_title_is_read_as_english() -> None:
    """Тега языка нет, а заголовок английский назвал - ярус тот же, что и по тегу."""
    tracks = (
        AudioTrack(index=0, language="rus", title="Дубляж"),
        AudioTrack(index=1, language="und", title="ENG DUB"),
    )

    assert ladder(tracks, EN) == [1, 0]


def test_an_unnamed_language_asks_the_product_and_not_a_guess() -> None:
    """Правило зовут и оттуда, где языку взяться неоткуда: тогда лестница остаётся русской."""
    assert ladder(ANIME, "") == ladder(ANIME, RU)


def test_the_default_track_takes_the_language_from_the_product_and_not_from_its_caller() -> None:
    """Ручку языка до отбора звука доносит слот: сценарии выбора её не передают вовсе."""
    media = Media(tracks=ANIME)

    _choose_tongue(EN)
    english = media.default_track()
    _choose_tongue(RU)

    assert (english, media.default_track()) == (2, 1)


def test_the_remembered_voice_survives_the_english_ladder() -> None:
    """🔴 Метка озвучки - ключ памяти: язык двигает ПОРЯДОК дорожек, а не их имена."""
    media = Media(tracks=ANIME)
    remembered = "rus · Дубляж"

    _choose_tongue(EN)
    found = media.find_voice(remembered)
    _choose_tongue(RU)

    assert [track.label for track in ANIME] == [
        "jpn · Original",
        "rus · Дубляж",
        "eng · Dub",
        "rus · Комментарии режиссёра",
    ]
    assert (found, media.find_voice(remembered)) == (1, 1)
