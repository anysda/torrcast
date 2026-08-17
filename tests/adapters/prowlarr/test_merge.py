"""Проверяет склейку выдач: одна раздача - одна строка, поля выбраны, а не пойманы."""

from itertools import permutations
from typing import Final

from torrcast.adapters.prowlarr.merge import merge
from torrcast.adapters.prowlarr.raw_result import RawResult
from torrcast.adapters.prowlarr.to_releases import to_releases


def _mirror(title: str, seeders: int, indexer: str, size: int = 8_000_000_000) -> RawResult:
    """Одна и та же раздача глазами разных индексеров: hash общий, данные врозь."""
    return RawResult(title=title, info_hash="a" * 40, size=size, seeders=seeders, indexer=indexer)


#: Живой случай с сырых пулов: один индексер видит у раздачи 2 сида, другой 26, третий
#: зовёт её иначе. До TC-239 в выдачу шла строка того, кто ответил первым.
_ONE_TORRENT: Final = (
    _mirror("Дюна: Пророчество / Dune: Prophecy (2024) WEB-DL 1080p", 2, "Knaben"),
    _mirror("Дюна: Пророчество / Dune: Prophecy (2024) WEB-DL 1080p", 26, "RuTor", 8_000_000_512),
    _mirror("Dune Prophecy S01 2024 1080p WEB-DL", 9, "Nyaa.si", 8_000_001_024),
)


def test_склейка_не_зависит_от_порядка_прихода_индексеров() -> None:
    """Кто ответил первым - дело сети, а не каталога: строка раздачи обязана совпасть
    при любом порядке ответов, иначе на телевизор едет то один файл, то другой.
    """
    snapshots = {
        tuple(
            (row.title, row.seeders, row.size, row.indexer, row.copies)
            for row in merge(*([item] for item in order))
        )
        for order in permutations(_ONE_TORRENT)
    }
    assert len(snapshots) == 1


def test_склейка_берёт_максимум_сидов_и_имя_по_большинству() -> None:
    """Рой у раздачи ОДИН - расхождение в сидах это разное время скрейпа, поэтому цифра
    берётся самая свежая. Имя - по большинству, тем же правилом, что у канона картины:
    оно не обязано приехать той же строкой, что и максимум сидов.
    """
    (merged,) = merge(*([item] for item in _ONE_TORRENT))
    assert merged.seeders == 26
    assert merged.title == "Дюна: Пророчество / Dune: Prophecy (2024) WEB-DL 1080p"
    assert merged.copies == 3  # сколько РАЗНЫХ индексеров привезли раздачу - счёт прежний


def test_склейка_разводит_ничью_имён_короче_и_по_алфавиту() -> None:
    """Двое индексеров - обычное дело, и большинства там не бывает. Ничья разводится
    так же, как в кластеризации, а не по тому, чей ответ приехал раньше.
    """
    pair = (_mirror("Психо", 5, "Knaben"), _mirror("Psycho", 7, "RuTor"))
    names = {merge(*([item] for item in order))[0].title for order in permutations(pair)}
    assert names == {"Психо"}


#: Аниме-раздача, которую зеркалят общий индексер и Nyaa. Имя от общего выигрывает
#: склейку, и про аниме оно не говорит ни слова - ни жанра, ни OVA, ни метки [TV].
_ANIME_MIRROR: Final = (
    _mirror("Cyberpunk Edgerunners S01 BD 1080p x264 FLAC", 40, "Knaben"),
    _mirror("Cyberpunk Edgerunners S01 BD 1080p x264 FLAC", 12, "Knaben"),
    _mirror("[Shiniori-Raws] Cyberpunk Edgerunners (BD 1080p)", 31, "Nyaa.si"),
)


def test_склейка_помнит_всех_принёсших_индексеров() -> None:
    """Кто привёз раздачу - не то же самое, что чья строка выиграла имя. Nyaa стоит в
    алфавите позже общего индексера и на склейке проигрывает всегда, поэтому имена
    принёсших переезжают целиком, а не сводятся к счётчику копий.
    """
    (merged,) = merge(*([item] for item in _ANIME_MIRROR))
    assert merged.indexer == "Knaben"  # чья строка выиграла имя - как и было
    assert merged.indexers == ("Knaben", "Nyaa.si")


def test_аниме_признак_переживает_склейку_с_общим_индексером() -> None:
    """Раздача с Nyaa - аниме, кто бы ни выиграл имя: у Nyaa аниме всё, что там лежит.
    Пока признак читался у строки-победителя, аниме с общего индексера выглядело обычным
    кино - и прикидка битрейта судила его порогом, писанным по игровому полному метру.
    """
    for order in permutations(_ANIME_MIRROR):
        (release,) = to_releases(merge(*([item] for item in order)))
        assert release.anime, release.raw_name


#: Один торрент под двумя именами (TC-382): у строки Nyaa метка внешней дорожки
#: ``[RUS(ext)]``, у строки общего индексера её нет - а торрент один и тот же.
_EXT_MIRROR: Final = (
    _mirror("Naruto [TV] [E220 of 220] [2002 ... DVDRip] | L2, L1", 91, "Knaben"),
    _mirror(
        "Наруто (S1) / Naruto [TV] [E220 of 220] [RUS(ext), ENG, JAP+Sub] [2002 ... DVDRip]",
        90,
        "Nyaa.si",
    ),
)


def test_склейка_помнит_все_имена_раздачи() -> None:
    """Имя победителя - одно, но сказанное каталогом об одной раздаче складывается:
    все её имена переезжают целиком, а не выбираются вместе с победившим."""
    (merged,) = merge(*([item] for item in _EXT_MIRROR))
    assert merged.title == "Naruto [TV] [E220 of 220] [2002 ... DVDRip] | L2, L1"
    assert set(merged.names) == {item.title for item in _EXT_MIRROR}


def test_метка_внешней_дорожки_переживает_склейку() -> None:
    """Метка ``RUS(ext)`` проигравшего имени - всё ещё факт об этой раздаче: честная
    строка про звук обязана сказать «перевод отдельным файлом», в каком бы порядке
    ни ответили индексеры."""
    for order in permutations(_EXT_MIRROR):
        (release,) = to_releases(merge(*([item] for item in order)))
        assert release.external_dub, release.raw_name


def test_внешняя_дорожка_озвучкой_не_считается_и_после_склейки() -> None:
    """🔴 TC-191 при этом в силе: метка внешней дорожки - не обещание русского звука,
    и склейка имён её в озвучку не превращает."""
    for order in permutations(_EXT_MIRROR):
        (release,) = to_releases(merge(*([item] for item in order)))
        assert not release.dubbed, release.raw_name


def test_склейка_берёт_размер_по_большинству() -> None:
    """Размер идёт в прикидку битрейта напрямую, поэтому его судит то же большинство,
    что и имя: цифра, которую сообщили чаще. Строка-победитель выиграла ИМЯ, а не
    размер - у неё он просто от того индексера, кто первым стоит в алфавите.
    """
    rows = (
        _mirror("Психо / Psycho (1960) DVDRip", 5, "Knaben", 8_000_000_000),
        _mirror("Психо / Psycho (1960) DVDRip", 6, "Nyaa.si", 8_100_000_000),
        _mirror("Psycho (1960) DVDRip", 7, "RuTor", 8_100_000_000),
    )
    (merged,) = merge(*([item] for item in rows))
    assert merged.size == 8_100_000_000


def test_склейка_разводит_ничью_размеров_в_большую_сторону() -> None:
    """Большинства у двоих зеркал не бывает, а промах в сторону тяжести дёшев: потолок
    битрейта и перекод для того и стоят. Заниженный размер пропустил бы неподъёмную
    раздачу мимо ворот - поэтому при равном счёте берётся большая цифра.
    """
    pair = (
        _mirror("Психо / Psycho (1960) DVDRip", 5, "Knaben", 8_000_000_000),
        _mirror("Психо / Psycho (1960) DVDRip", 6, "RuTor", 8_100_000_000),
    )
    sizes = {merge(*([item] for item in order))[0].size for order in permutations(pair)}
    assert sizes == {8_100_000_000}


def test_склейка_не_считает_молчание_о_размере_голосом() -> None:
    """Нулевой размер - это «индексер не сказал», а не «раздача ничего не весит»:
    в большинстве он не участвует, иначе двое молчунов обнуляли бы честную цифру.
    """
    rows = (
        _mirror("Психо / Psycho (1960) DVDRip", 5, "Knaben", 0),
        _mirror("Психо / Psycho (1960) DVDRip", 6, "Nyaa.si", 8_000_000_000),
        _mirror("Psycho (1960) DVDRip", 7, "RuTor", 0),
    )
    (merged,) = merge(*([item] for item in rows))
    assert merged.size == 8_000_000_000


def test_склейка_не_зависит_от_разбивки_строк_по_пачкам() -> None:
    """Порядок индексеров проверен перестановками выше; тут - порядок строк ВНУТРИ:
    одна пачка на всех и по пачке на индексера обязаны дать тот же выход побайтово.
    """
    one_batch = merge(list(_ONE_TORRENT))
    per_indexer = merge(*([item] for item in _ONE_TORRENT))

    def snapshot(rows: list[RawResult]) -> list[tuple[str, int, int, str, int]]:
        return [(row.title, row.seeders, row.size, row.indexer, row.copies) for row in rows]

    assert snapshot(one_batch) == snapshot(per_indexer)


def test_разные_раздачи_остаются_разными() -> None:
    """Тождество тут ровно одно - ``infoHash``: похожие имена раздач не склеивают."""
    rows = [
        RawResult("Матрица (1999) 1080p", "a" * 40, 1, 2, "Knaben"),
        RawResult("Матрица (1999) 1080p", "b" * 40, 1, 2, "RuTor"),
    ]
    assert len(merge(rows)) == 2
