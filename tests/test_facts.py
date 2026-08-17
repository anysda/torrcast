"""Фасад справки: прежние имена ведут в новые дома и работают в живом меню.

Правила разбора статьи проверяет ``tests/domain/facts``, сеть и файлы -
``tests/adapters/wiki``, сценарии - ``tests/usecases``, проводку и справку меню -
``tests/runtime``. Здесь остаётся то, ради чего фасад и существует: прежние имена на
месте и меню печатает справку ровно так, как печатало.

⚠️ В сеть отсюда не ходят: всё, что спрашивается у фасада, заранее лежит в его кэше, а
кэш разведён по каталогам состояния (``TORRCAST_STATE`` ставит общая фикстура).
"""

from __future__ import annotations

from tests.articles import MOANA
from torrcast import cli
from torrcast import facts as facts_mod
from torrcast.facts import Fact, Facts, Origin, origin, shorten
from torrcast.runtime.facts_wiring import FACTS
from torrcast.runtime.menu_facts import MenuFacts


def test_every_exported_name_is_the_one_from_its_home() -> None:
    """Фасад отдаёт те же объекты, а не свои копии."""
    assert facts_mod.FACTS is FACTS
    assert Facts is MenuFacts
    assert origin == FACTS.passport.of
    assert facts_mod.origin_either == FACTS.passport.either.of
    assert facts_mod.get_json == FACTS.client.get
    assert all(hasattr(facts_mod, name) for name in facts_mod.__all__)


def test_the_passport_entry_point_answers_from_the_same_cache() -> None:
    """``origin`` - тонкий вход в тот же сценарий, а не вторая реализация."""
    stored = Origin(title="Cars", year=2006, name="Тачки", source=facts_mod.SOURCE_WIKI)
    FACTS.cache.write("Тачки", False, stored)
    FACTS.cache.write("Тачки", None, stored)

    assert origin("Тачки", False, budget=0.0) == stored
    assert origin("Тачки", None, budget=0.0) == stored, "режим «оба типа» - свой ряд ключей"
    assert FACTS.cache.read("Тачки", False) == stored
    assert FACTS.cache.read("Тачки", True) is None


def test_menu_prints_the_old_line_when_there_is_no_help() -> None:
    """Без справки меню — ровно тот же список, что и до неё."""
    from tests.test_cli import _moana_franchise

    plans = _moana_franchise()
    assert cli.menu_lines(plans, None, width=80) == (
        "  1. Моана: романтика золотого века (1926)\n  2. Моана (2016)\n  3. Моана 2 (2024)"
    )


def test_menu_puts_rating_and_time_in_the_head_and_the_plot_below() -> None:
    """Со справкой: рейтинг с источником и хронометраж в строке названия, описание — под."""
    from tests.test_cli import _moana_franchise

    plans = _moana_franchise()
    facts = Facts([])
    facts.start()
    facts.found = {("Моана", 2016): Fact(about=MOANA, rating="IMDb 7.6", runtime="1 ч 47 мин")}
    printed = cli.menu_lines(plans, facts, width=80).splitlines()
    assert printed[0] == "  1. Моана: романтика золотого века (1926)"
    assert printed[1] == "  2. Моана (2016) · IMDb 7.6 · 1 ч 47 мин"
    assert printed[2].startswith("     «Моа́на» (англ. Moana) — американский")
    assert printed[-1] == "  3. Моана 2 (2024)", "у остальных справки нет - и лишних строк нет"


def test_the_description_wraps_by_words_under_the_terminal() -> None:
    """Описание переносится по словам, каждая строка — с тем же отступом и в ширину."""
    from tests.test_cli import _moana_franchise

    facts = Facts([])
    facts.start()
    facts.found = {("Моана", 2016): Fact(about=MOANA)}
    printed = cli.menu_lines(_moana_franchise(), facts, width=60).splitlines()
    blurb = [line for line in printed if line.startswith("     ")]
    assert len(blurb) > 1, "фраза не влезла в одну строку - значит, перенеслась"
    assert all(len(line) < 60 for line in blurb), "строка не должна вылезать за терминал"
    assert not any(line.endswith("-") for line in blurb), "перенос по словам, не по дефису"
    assert " ".join(line.strip() for line in blurb) == MOANA, "фраза цела и ничем не обрезана"


def test_the_blurb_of_the_menu_is_the_first_sentence_of_the_article() -> None:
    """Фасад отдаёт ту же обрезку, которой меню печатает описание."""
    assert shorten(MOANA).endswith("Walt Disney Pictures.")
