"""🔴 TC-953. Строки про озвучку обязаны называть язык, который продукт ИЩЕТ.

Язык в надпись попадает через сам каталог: и отбор (``spoken = language or tongue()``
в :meth:`torrcast.domain.media.Media.default_track`), и надпись
(:func:`torrcast.domain.catalogs.phrase.phrase`) читают один и тот же слот языка
продукта (:func:`torrcast.domain.catalogs.tongue.tongue`). Поэтому язык подписи и язык
искомой озвучки совпадают всегда, и предмет поиска пишется литералом СВОЕГО каталога:
английский ищет English dub, русский - русскую озвучку. Литерал «Russian» в английском
каталоге - враньё зрителю ``cast --en``: ему искали английский дубляж, а надпись
называла русский (живой случай владельца: «looking for a Russian dub» при играющем
``eng``).
"""

from __future__ import annotations

from torrcast.domain.catalogs.cmd_play.en import en as cmd_play_en
from torrcast.domain.catalogs.cmd_play.ru import ru as cmd_play_ru
from torrcast.domain.catalogs.digest.en import en as digest_en
from torrcast.domain.catalogs.digest.ru import ru as digest_ru
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.rank.en import en as rank_en
from torrcast.domain.catalogs.rank.ru import ru as rank_ru
from torrcast.domain.catalogs.select_bench.en import en as select_bench_en
from torrcast.domain.catalogs.select_bench.ru import ru as select_bench_ru

#: Ключи, чья надпись называет предмет поиска озвучки, с текстами обоих каталогов.
#: Английский текст обязан звать английский дубляж, русский - русский; слово «Russian»
#: в английском каталоге здесь - зашитое враньё, а не перевод.
_VOICE_LINES: tuple[tuple[str, str, str], ...] = tuple(
    (key, english[key], russian[key])
    for english, russian, keys in (
        (
            select_bench_en(),
            select_bench_ru(),
            (
                "select_bench.voice_search_phase",
                "select_bench.reason_no_russian_voice",
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


def test_the_english_catalog_names_the_english_dub() -> None:
    offenders = [
        f"{key!r}: en {en_text!r}"
        for key, en_text, _ in _VOICE_LINES
        if "English" not in en_text or "russian" in en_text.casefold()
    ]
    assert offenders == [], f"английская надпись зовёт не тот дубляж: {offenders}"


def test_the_russian_catalog_still_names_the_russian_dub() -> None:
    offenders = [
        f"{key!r}: ru {ru_text!r}" for key, _, ru_text in _VOICE_LINES if "русск" not in ru_text
    ]
    assert offenders == [], f"русская надпись потеряла русский дубляж: {offenders}"


def test_the_choice_note_counts_by_tag_not_by_a_literal() -> None:
    english, russian = rank_en(), rank_ru()
    assert "{tag}" in english["rank.voice_note"], "тег языка - значение, а не литерал"
    assert "{tag}" in russian["rank.voice_note"]
    assert "russian" not in english["rank.voice_ours"].casefold()
    assert english["rank.voice_tag"] == "eng" and russian["rank.voice_tag"] == "rus"


def test_the_release_name_key_no_longer_claims_russian() -> None:
    """Ключ говорит про разбор имени раздачи, и «russian» в его имени - то же враньё."""
    english, russian = rank_en(), rank_ru()
    assert "rank.no_language_tag_russian" not in english
    assert "rank.no_language_tag_russian" not in russian
    assert "rank.no_language_tag_dub_by_name" in english
    assert "rank.no_language_tag_dub_by_name" in russian


def test_the_search_phase_line_names_the_sought_language(_english: None) -> None:
    """Дословная строка владельца: ``cast --en`` ищет английский дубляж."""
    assert phrase("select_bench.voice_search_phase", number=2, total=24) == (
        "looking for an English dub: release 2 of 24 - "
    )


def test_the_search_phase_line_in_russian_is_untouched(_russian_product: None) -> None:
    assert phrase("select_bench.voice_search_phase", number=2, total=24) == (
        "ищу русскую озвучку: релиз 2 из 24 - "
    )
