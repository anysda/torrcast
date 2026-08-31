"""🔴 TC-953, TC-958. Строки про озвучку называют то, что продукт ИЩЕТ, - дорожку на
языке ЗРИТЕЛЯ, а не дубляж.

Язык зрителя - это язык продукта: и гейт (:func:`torrcast.usecases.rank.voice_unproven.
voice_unproven`), и лестница (:func:`torrcast.domain.voice_order._tier`), и надпись
(:func:`torrcast.domain.catalogs.phrase.phrase`) читают один и тот же слот
(:func:`torrcast.domain.catalogs.tongue.tongue`). Поэтому надпись обязана следовать за
языком продукта: под английской ручкой ищется и называется английский звук, под русской -
русский. Литерал «Russian» в английском каталоге - враньё зрителю ``cast --en`` (живой
случай владельца: «looking for a Russian dub» при играющем ``eng``).

А слово «dub» в английских строках врёт независимо от языка в скобках: ярус меряет не
дубляж, а дорожку на языке зрителя, и для фильма, снятого по-английски, английская
дорожка - оригинал, а не дубляж. «No English dub (English)» отрицало тот самый звук,
который продукт затем включал, - поэтому искомое зовётся English voice, и сторож ниже
держит именно связь «надпись следует за языком продукта», а не снимок литералов: строки
спрашиваются через ``phrase()`` при обоих языках.
"""

from __future__ import annotations

from tests.usecases.rank.releases import media, track
from torrcast.domain.catalogs.cmd_play.en import en as cmd_play_en
from torrcast.domain.catalogs.cmd_play.ru import ru as cmd_play_ru
from torrcast.domain.catalogs.digest.en import en as digest_en
from torrcast.domain.catalogs.digest.ru import ru as digest_ru
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.rank.en import en as rank_en
from torrcast.domain.catalogs.rank.ru import ru as rank_ru
from torrcast.domain.catalogs.select_bench.en import en as select_bench_en
from torrcast.domain.catalogs.select_bench.ru import ru as select_bench_ru
from torrcast.domain.catalogs.tongue import EN, RU, _choose_tongue
from torrcast.usecases.rank.sought_voice import sought_voice
from torrcast.usecases.rank.voice_unproven import voice_unproven

#: Ключи, чья надпись называет предмет поиска озвучки, с текстами обоих каталогов.
_VOICE_LINES: tuple[tuple[str, str, str], ...] = tuple(
    (key, english[key], russian[key])
    for english, russian, keys in (
        (
            select_bench_en(),
            select_bench_ru(),
            (
                "select_bench.voice_search_phase",
                "select_bench.reason_no_voice",
                "select_bench.honest_no_voice_note",
                "select_bench.voiceless_head",
                "select_bench.mute_fallback_note",
                "select_bench.recheck_no_voice_note",
                "select_bench.refusal_no_voice",
            ),
        ),
        (cmd_play_en(), cmd_play_ru(), ("cmd_play.voice_apart",)),
        (digest_en(), digest_ru(), ("digest.mute",)),
    )
    for key in keys
)

#: Значения-заглушки под все плейсхолдеры этих ключей: ``str.format`` лишние терпит.
_VALUES = {
    "number": 1,
    "total": 2,
    "tried": 2,
    "count": 2,
    "checked": 2,
    "release": 1,
    "lang": "Japanese",
    "base": "voice.mka",
    "stamp": "",
}


def test_the_caption_follows_the_product_language() -> None:
    """Одна и та же строка через ``phrase()``: под EN - английский текст, под RU - русский."""
    offenders = []
    for key, en_text, ru_text in _VOICE_LINES:
        _choose_tongue(EN)
        if phrase(key, **_VALUES) != en_text.format(**_VALUES):
            offenders.append(f"{key!r}: под EN надпись не из английского каталога")
        _choose_tongue(RU)
        if phrase(key, **_VALUES) != ru_text.format(**_VALUES):
            offenders.append(f"{key!r}: под RU надпись не из русского каталога")
    assert offenders == [], f"надпись не следует за языком продукта: {offenders}"


def test_the_english_catalog_names_the_english_voice_not_a_dub() -> None:
    """Искомое под EN - английский ЗВУК: оригинал англоязычной картины дубляжем не бывает."""
    offenders = [
        f"{key!r}: en {en_text!r}"
        for key, en_text, _ in _VOICE_LINES
        if "English voice" not in en_text or "dub" in en_text.casefold()
    ]
    offenders += [
        f"{key!r}: en {en_text!r}"
        for key, en_text, _ in _VOICE_LINES
        if "russian" in en_text.casefold()
    ]
    assert offenders == [], f"английская надпись зовёт не тот голос: {offenders}"


def test_the_russian_catalog_still_names_the_russian_dub() -> None:
    offenders = [
        f"{key!r}: ru {ru_text!r}" for key, _, ru_text in _VOICE_LINES if "русск" not in ru_text
    ]
    assert offenders == [], f"русская надпись потеряла русскую озвучку: {offenders}"


def test_the_gate_seeks_the_same_language_the_caption_names() -> None:
    """Гейт и надпись ищут одно: английская дорожка годна под EN, русская - под RU."""
    english = media(tracks=(track(0, "eng", "Original"),))
    russian = media(tracks=(track(0, "rus", "Дубляж"),))
    _choose_tongue(EN)
    assert sought_voice(english) and not voice_unproven(english)
    assert voice_unproven(russian), "русская дорожка английскому зрителю годностью не считается"
    _choose_tongue(RU)
    assert sought_voice(russian) and not voice_unproven(russian)
    assert voice_unproven(english)


def test_the_choice_note_counts_by_tag_not_by_a_literal() -> None:
    english, russian = rank_en(), rank_ru()
    assert "{tag}" in english["rank.voice_note"], "тег языка - значение, а не литерал"
    assert "{tag}" in russian["rank.voice_note"]
    assert "russian" not in english["rank.voice_ours"].casefold()
    assert english["rank.voice_tag"] == "eng" and russian["rank.voice_tag"] == "rus"


def test_no_key_names_another_language_than_the_line_does() -> None:
    """Ключ со «russian» в имени при нерусском тексте - то же враньё, только в имени."""
    for catalog in (rank_en(), rank_ru()):
        assert "rank.no_language_tag_russian" not in catalog
        assert "rank.no_language_tag_dub_by_name" in catalog
    for catalog in (select_bench_en(), select_bench_ru()):
        assert "select_bench.reason_no_russian_voice" not in catalog
        assert "select_bench.reason_no_voice" in catalog


def test_the_search_phase_line_names_the_sought_language() -> None:
    """Дословная строка владельца: под ``--en`` ищется английский звук, под ``--ru`` - русский."""
    _choose_tongue(EN)
    assert "English" in phrase("select_bench.voice_search_phase", number=2, total=24)
    _choose_tongue(RU)
    assert "русск" in phrase("select_bench.voice_search_phase", number=2, total=24)
