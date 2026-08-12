"""Часть разбора имён; публичный фасад — :mod:`torrcast.parse`."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.episodes import parse_episode as parse_episode
    from torrcast.franchise import _aliases as _aliases
    from torrcast.franchise import _by_words as _by_words
    from torrcast.franchise import _franchise_item_key as _franchise_item_key
    from torrcast.franchise import _group_weight as _group_weight
    from torrcast.franchise import _numbered_line as _numbered_line
    from torrcast.franchise import _words as _words
    from torrcast.franchise import franchises as franchises
    from torrcast.parse_name import _ALTERNATIVE_PICTURE_RE as _ALTERNATIVE_PICTURE_RE
    from torrcast.parse_name import _ALTERNATIVE_TITLE_RE as _ALTERNATIVE_TITLE_RE
    from torrcast.parse_name import _AV1_RE as _AV1_RE
    from torrcast.parse_name import _BRACKETS_RE as _BRACKETS_RE
    from torrcast.parse_name import _CODEC_TOKEN_RE as _CODEC_TOKEN_RE
    from torrcast.parse_name import _COLLECTION_CUT_RE as _COLLECTION_CUT_RE
    from torrcast.parse_name import _CYRILLIC as _CYRILLIC
    from torrcast.parse_name import _EPISODE_COUNT_RE as _EPISODE_COUNT_RE
    from torrcast.parse_name import _EPISODE_SPAN_RES as _EPISODE_SPAN_RES
    from torrcast.parse_name import _FANSUB_EPISODE_RE as _FANSUB_EPISODE_RE
    from torrcast.parse_name import _H264_RE as _H264_RE
    from torrcast.parse_name import _HEVC_RE as _HEVC_RE
    from torrcast.parse_name import _LATIN as _LATIN
    from torrcast.parse_name import _MPEG4_RE as _MPEG4_RE
    from torrcast.parse_name import _NON_VIDEO_RE as _NON_VIDEO_RE
    from torrcast.parse_name import _NUMERO_RE as _NUMERO_RE
    from torrcast.parse_name import _OPEN_BRACKET_RE as _OPEN_BRACKET_RE
    from torrcast.parse_name import _RU_CUT_WORDS as _RU_CUT_WORDS
    from torrcast.parse_name import _SEASON_ONLY_RES as _SEASON_ONLY_RES
    from torrcast.parse_name import _SEASON_SPAN_RES as _SEASON_SPAN_RES
    from torrcast.parse_name import _SERIES_HINT_RE as _SERIES_HINT_RE
    from torrcast.parse_name import _SOURCES as _SOURCES
    from torrcast.parse_name import _TAG_ONLY_RE as _TAG_ONLY_RE
    from torrcast.parse_name import _TAG_VOICES as _TAG_VOICES
    from torrcast.parse_name import _TITLE_CUT_RE as _TITLE_CUT_RE
    from torrcast.parse_name import _TITLE_TAIL_RE as _TITLE_TAIL_RE
    from torrcast.parse_name import _UKRAINIAN as _UKRAINIAN
    from torrcast.parse_name import _VIDEO_MARKER_RE as _VIDEO_MARKER_RE
    from torrcast.parse_name import _VOICES as _VOICES
    from torrcast.parse_name import _YEAR_PATTERNS as _YEAR_PATTERNS
    from torrcast.parse_name import Picture as Picture
    from torrcast.parse_name import franchise_key as franchise_key
    from torrcast.parse_name import in_digits as in_digits
    from torrcast.parse_name import slugify as slugify
    from torrcast.parse_name import spell as spell
    from torrcast.parse_name import split_franchise_index as split_franchise_index


import re
import unicodedata
from typing import Final


def pick_franchise(query: str, pictures: list[Picture]) -> list[Picture]:
    """``«матрица 2»`` → [«Матрица: Перезагрузка»]; без номера — вся франшиза. Ищем по
    каноническому ключу (русскому или оригинальному), затем по вхождению подстроки, а
    в последнюю очередь по словам (:func:`_by_words`); номер — индекс в хронологии, а не
    часть названия.
    """
    groups = franchises(pictures)
    aliases = _aliases(groups)
    # Каноническим именем картины становится то, которым её подписало БОЛЬШИНСТВО раздач,
    # и на «двенадцати обезьянах» это «12 обезьян» - цифрой. Спросили же прописью, поэтому
    # ключи ищутся ещё и в цифровой записи (:func:`in_digits`).
    digits = {in_digits(key): key for key in groups}
    # Одно и то же имя переносят в русский по-разному: «Зена - королева воинов / Xena»
    # лежит под одним написанием, а спрашивают её «Ксена» - тем же ``Xena``, только
    # перенесённым иначе. Нормализованная транслитерация (:func:`spell`) сводит обе записи
    # к одной строке.
    #
    # 🔴 Указатель строится по ОРИГИНАЛАМ (``aliases``), а не по русским ключам каталога.
    # Пару языков должна назвать сама раздача: транслит одного лишь русского имени - это
    # наша догадка о том, как его напишут латиницей, и ручаться ею за картину нельзя.
    spelled: dict[str, str] = {}
    for written, target in sorted(aliases.items()):
        spelled.setdefault(spell(written), target)
    # Третьи имена из заголовков раздач («Дикие истории / Relatos salvajes / Wild Tales»)
    # - тоже подпись каталога, только слабее оригинала: раздача назвала это имя, но не
    # поставила его ни названием картины, ни оригиналом. Точное совпадение с ним сильнее
    # НЕСТРОГИХ ступеней ниже (вхождение в чужой ключ, слова, звучание): «wild tales» -
    # это «Дикие истории» 2014 года, а не сериал ``Wild Tales From The Farm``, чей ключ
    # лишь содержит запрос подстрокой. Спор двух франшиз за одно третье имя не решаем -
    # ровно как в :func:`_by_alias`, честное «не нашлось» лучше однофамильца.
    third: dict[str, str] = {}
    for group_key, items in groups.items():
        for picture in items:
            for slug in picture.aliases:
                if not slug or slug in groups or slug in aliases:
                    continue
                if third.setdefault(slug, group_key) != group_key:
                    third[slug] = ""

    def named(name: str) -> str | None:
        """Ключ, которым каталог подписал картину ЦЕЛИКОМ: та же строка, её латинский
        двойник или она же цифрами. Нестрогих ступеней тут нет нарочно - на этот ответ
        опирается разбор «имя это или номер части» (:data:`_TITLE_NUMBER_RE` ниже).
        """
        wanted = slugify(name)
        if not wanted:
            return None
        pointed = aliases.get(wanted)
        if wanted in groups:
            # 🔴 TC-394. Имя может претендовать на ДВА места сразу: быть ключом своей
            # франшизы и указателем на чужую (оригинал другой картины). Однофамильцев
            # разводит вес - то же правило, что в :func:`_aliases`: «whiplash» - это
            # сериал-однофамилец 1961 года на одну раздачу и оригинал «Одержимости»
            # 2014-го на шесть десятков, и слово за тем, за кого каталог.
            if (
                pointed is not None
                and pointed != wanted
                and (_group_weight(groups, pointed) > _group_weight(groups, wanted))
            ):
                return pointed
            return wanted
        if pointed is not None:
            return pointed
        if (counted := in_digits(wanted)) in digits:
            return digits[counted]
        return None

    def lookup(name: str) -> str | None:
        if (exact := named(name)) is not None:
            return exact
        wanted = slugify(name)
        if not wanted:
            return None
        if pointed := third.get(wanted):
            return pointed
        if hits := [k for k in groups if wanted in k]:
            return min(hits, key=lambda key: (len(key), -_group_weight(groups, key), key))
        # Порядок слов и союзы - на совести человека, а не каталога (:func:`_by_words`).
        # Стоит выше грубого «ключ входит в запрос»: у «гарри поттер дары смерти» тот
        # находил франшизу «гарри поттер» и отсчитывал номер части по ней.
        if loose := _by_words(wanted, groups):
            return loose
        # Запрос длиннее канона: «киберпанк бегущие по краю» - это франшиза «киберпанк»
        # (подзаголовок после двоеточия в ключ не входит). Берём самое длинное совпадение.
        if hits := [k for k in groups if k and k in wanted]:
            return max(hits, key=len)
        # Последняя ступень - звучание (:data:`spelled`). Последняя нарочно: сверка по
        # звучанию отвечает, КАК имя произносится, а не как оно написано в каталоге, и
        # пока картину находит само написание, спрашивать больше не о чем. Транслит
        # русского имени («vrata shteyna») именно так и находит картину, подписанную
        # латиницей целиком, - вхождением, а не звучанием.
        return spelled.get(spell(wanted))

    name, index = split_franchise_index(query)
    key = lookup(name)
    if key is None:  # номер оказался частью названия: «пила 8», «форсаж 6»
        key, index = lookup(query), None
    if key is None:
        # Имени франшизы человек мог и не назвать: он зовёт картину подзаголовком или тем
        # именем, которое каталог поставил в заголовке третьим (:func:`_by_alias`).
        items = _by_subtitle(name, pictures) or _by_alias(name, pictures)
        if not items:
            items = _by_subtitle(query, pictures) or _by_alias(query, pictures)
            index = None
        if not items:
            # Слова запроса разошлись по двум именам картины - последняя и самая
            # нестрогая ступень, поэтому она идёт после псевдонимов (:func:`_by_alias`).
            items, index = _by_both_names(query, pictures), None
        return _numbered(items, index)

    franchise_items = _both_languages(groups, aliases, key)
    if index is None:
        continuation_groups = {
            grouped_key: [p for p in grouped_items if p.kind != "other"]
            for grouped_key, grouped_items in groups.items()
            if grouped_key.startswith(f"{key}-и-")
        }
        continuation_groups = {k: items for k, items in continuation_groups.items() if items}
        if len(continuation_groups) >= 2:
            continuations = [p for items in continuation_groups.values() for p in items]
            known = {p.key for p in continuations}
            franchise_items = sorted(
                [p for p in franchise_items if p.kind != "other" and p.key not in known]
                + continuations,
                key=_franchise_item_key,
            )
    items = _numbered(franchise_items, index)
    if not items and index is not None and (whole_name := named(query)) is not None:
        # 🔴 Номера в этой франшизе нет, а вся строка целиком - имя картины в каталоге:
        # значит цифра была частью названия. «Легенда 17» уходила во франшизу «легенда»
        # за семнадцатой частью, которой нет и быть не может, и человек читал «картин во
        # франшизе 2, номера 17 нет» при живой картине на девять десятков сидов. Тот же
        # класс, что «Kill Bill: Vol. 1», только показателя перед цифрой тут нет вовсе -
        # ручается за пару сам каталог, подписавший картину ровно этой строкой.
        #
        # Совпадение требуется ПОЛНОЕ (:func:`named`, без нестрогих ступеней): иначе
        # «матрица 7» находила бы франшизу вхождением и вместо честного «номера 7 нет»
        # выкладывала всю линейку.
        items = _both_languages(groups, aliases, whole_name)
    return _with_subtitled(items, name, pictures, index)


def catalog_has_name(query: str, pictures: list[Picture]) -> bool:
    """Подписана ли хоть одна картина каталога ТОЧНО именем запроса.

    Вопрос не «что похоже», а «есть ли оно тут»: по запросу «девять» каталог отвечает
    сотней строк про «Девять ярдов», «Девять песен» и «Девять королей», а самой «Девять»
    в ней нет - и это повод переспросить точнее, а не смириться с соседями по подстроке
    (:func:`~torrcast.cli._ceiling_reinforce`).

    Считается подписью: имя франшизы у ненумерованной или первой части, точное имя
    картины, её оригинал и подтверждённое несколькими раздачами третье имя. Нарочно НЕ
    считаются: одинокий сиквел, одиночный псевдоним, вхождение подстрокой и цифровая
    запись числительных (:func:`in_digits`): «9» и «Девять» - разные картины, и запрос
    словом не должен довольствоваться картиной, подписанной цифрой.
    """
    name, _index = split_franchise_index(query)
    wanted = slugify(name)
    if not wanted:
        return False
    for picture in pictures:
        if slugify(picture.title) == wanted:
            return True
        if picture.original and slugify(picture.original) == wanted:
            return True
        if franchise_key(picture.title) == wanted and picture.part in (None, 1):
            return True
        alias_support = sum(
            wanted in {slugify(alias) for alias in release.aliases} for release in picture.releases
        )
        if alias_support >= 2:
            return True
    return False


def _with_subtitled(
    items: list[Picture], name: str, pictures: list[Picture], index: int | None
) -> list[Picture]:
    """Картины, названные ПОДЗАГОЛОВКОМ, - вдобавок к найденным по ключу франшизы.

    🔴 TC-246. Подзаголовок читался только тогда, когда по ключу не нашлось ничего
    (:func:`_by_subtitle`), а найтись по ключу может огрызок. «Космическая одиссея» -
    это ключ картины 1987 года с одной мёртвой раздачей, и она забирала запрос себе
    целиком: «2001: Космическая одиссея» лежала в той же выдаче двумя десятками раздач,
    но её ключ - ``2001``, запрос в него не входит, и до меню она не доезжала вовсе.
    Человек читал «рой мёртв» по единственной раздаче чужой картины при 80 строках в
    пуле. Тот же класс - ``RahXephon`` при 76 строках.

    Берутся ОБЕ, а не одна вместо другой: имя человек назвал верно, и обе картины
    подписаны им честно - одна целиком, другая подзаголовком. Кому из них быть дефолтом,
    решает меню по живости (:func:`~torrcast.cli.first_alive`), а не порядок проверок
    здесь; смену видно и списком, и честной строкой.

    ⚠️ Номер части в запросе это выключает: номер отсчитывается по линейке франшизы, и
    добавленная в неё картина из чужой франшизы сдвинула бы нумерацию.
    """
    if index is not None or not items:
        return items
    keys = {p.key for p in items}
    return items + [p for p in _by_subtitle(name, pictures) if p.key not in keys]


def _numbered(items: list[Picture], index: int | None) -> list[Picture]:
    """Номер части из запроса → одна картина; номера нет — вся линейка как есть.

    🔴 TC-320. Считается номер по той же ЛИНЕЙКЕ, которой меню подписывает пункты
    (:func:`_numbered_line`), и состоит она только из КИНО. Две поправки к прежнему
    «index-й по хронологии», и обе об одном - чтобы номер отвечал картиной, а не тем,
    что оказалось на этом месте:

    * не-видео (``kind == "other"``: игры, саундтреки, книги) места в линейке не
      занимает. На «матрица 5» хронология выходила длиной в семь, пятым в ней стоял
      репак игры «Матрица: Путь Нео» на одну раздачу, и он же ехал в меню - при живых
      пятидесяти семи раздачах «Воскрешения» рядом. Из каталога это не-видео не
      выбрасывает: без номера части франшиза показывается как была;
    * то, что каталог номером не подписал, номером и не отвечает. Хронология - догадка,
      и годится она, пока каталог не назвал номеров вовсе («Гарри Поттер»): тогда
      линейка и есть вся хронология, как раньше. Назвал - линейку держат названные
      номера плюс свободное первое место, а всё прочее уходит за неё, и меню зовёт его
      «без номера части». У «Матрицы» подписаны части со второй по четвёртую, линейка
      кончается на них, и пятой в ней нет, как её ни считай;
    * явный номер сильнее позиции, но за него ручается ГОД носителя. Безгодовый
      претендент («Матрица 4 - As It Should Be», фанатская сборка на двух раздачах)
      держится на одной цифре в имени, и живой настоящей части - новее последней
      подписанной и полнее его кучкой - не соперник: номер отвечает ею
      (:func:`_living_part`).

    Пустой ответ тут не потеря, а честная строка «картин во франшизе N, номера K нет»
    (:func:`~torrcast.cli._nothing`): молча показать вместо просимой части соседнюю -
    ровно та подмена картины, которой быть не должно.

    ⚠️ У сериала номер отсчитывается СЕЗОНОМ, а не частью франшизы
    (:func:`reads_season`), и линейка частей его не касается вовсе.
    """
    if index is None:
        return items
    if reads_season(items):
        return [p for p in items if p.kind == "tv"]
    line = _numbered_line([p for p in items if p.kind != "other"])[0]
    # Явный номер части сильнее позиции: «тачки 2» → «Тачки 2», а не спин-офф.
    explicit = [p for p in line if p.part == index]
    if explicit:
        best = max(explicit, key=lambda p: len(p.releases))
        alternative = bool(best.releases) and all(
            _ALTERNATIVE_PICTURE_RE.search(r.raw_name)
            or _ALTERNATIVE_TITLE_RE.search(r.raw_name.split(" / ", 1)[0])
            for r in best.releases
        )
        if best.year is not None and not alternative:
            return [best]
        # 🔴 TC-335. Безгодовый носитель явного номера сам за себя не ручается: «Матрица 4
        # / Matrix 4 - As It Should Be» - фанатская перемонтажка на двух раздачах, и год
        # каталог ей назвать не смог. Живая настоящая часть рядом («Матрица: Воскрешение»,
        # 57 раздач) такому номеру не проигрывает - иначе человек, просивший четвёртую
        # часть известной франшизы, получает любительский перемонтаж.
        rival = _living_part(items, line, index, best)
        if rival is not None:
            return [rival]
        return [best]
    if not 1 <= index <= len(line):
        return []
    # В линейке бывают дыры: назван номер 2 и номер 5, а третьей и четвёртой в выдаче
    # нет. Пятая стоит на третьем месте, но третьей частью от этого не становится.
    found = line[index - 1]
    return [] if found.part is not None else [found]


def reads_season(pictures: list[Picture]) -> bool:
    """Номер при этом имени - СЕЗОН сериала, а не номер части франшизы.

    🔴 TC-363. У сериала частей не бывает - бывают сезоны, и номер к нему приложен
    человеком именно так. Прежде номер отсчитывался по хронологии всего, что нашлось под
    именем, и «chainsaw man 2» отвечал полнометражным фильмом к сериалу («Человек-бензопила.
    Фильм: История Резе», 65 раздач), а «chainsaw man 3» - его же безгодовым латинским
    дублем на 4 раздачи. Человек просил второй сезон, а получал кино; просил третий -
    получал ту же картину под другим именем.

    Признак берётся у каталога, а не у догадки, и условий два:

    * франшизу НАЧИНАЕТ сериал - самая ранняя картина под этим именем и есть он. Тогда имя
      носит сериал, а полный метр к нему приложен, как «История Резе» к «Человеку-бензопиле»;
    * ни одну картину каталог не подписал номером части. Подписал («Форсаж 5», «Пила 8»,
      «Легенда 17») - номер и есть номер части, а цифра в имени сама за себя ручается.

    ⚠️ Первенство сериала тут не украшение, а ограждение, и мерено оно на сохранённых
    выдачах: сериал попадается в хвосте у половины киношных франшиз (документальный «Титаник»
    2012 года, «Гарри Поттер: Турнир факультетов Хогвартса», мультсериал «Джуманджи» 1996-го).
    Хватило бы одного его присутствия - и «гарри поттер 1» отвечал бы кулинарным шоу вместо
    фильма, а «титаник 3» - документалкой вместо картины 1997 года.

    Не-видео (игры, саундтреки) в счёт не идёт ни с одной стороны: «Ведьмак 3» на полке -
    игра, а не третья часть франшизы, и месту в линейке она не соперник (:func:`_numbered`).

    Отвечают на такой номер сериалы франшизы, а фильмы к ним - нет: спрошен сезон, и
    подставить вместо него полный метр значило бы показать другое кино. Есть ли такой сезон
    в выдаче - вопрос следующий и отвечает на него сезонная машинерия
    (:func:`~torrcast.cli.season_gaps`, :func:`~torrcast.cli._season_reinforce`), вплоть до
    честного «раздач с сезоном N нет».
    """
    line = [p for p in pictures if p.kind != "other"]
    if not line or any(p.part is not None for p in line):
        return False
    return min(line, key=_franchise_item_key).kind == "tv"


def _living_part(
    items: list[Picture], line: list[Picture], index: int, claimant: Picture
) -> Picture | None:
    """Живая настоящая часть против безгодового носителя явного номера, либо ``None``.

    Раз решиться может только сверкой с живостью кучки: безгодовый претендент
    (фанатская сборка вроде «Матрица 4 - As It Should Be») держится ровно на одном
    признаке - цифре в имени. Против него играет безномерная картина, которая:

    * НОВЕЕ последней подписанной номером части (года претендента нет, и мерить
      хронологию приходится от тех номеров, за которые каталог поручился и годом);
    * ЖИВЕЕ самого претендента - самая полная кучка среди таких. Сборка на двух
      раздачах пятидесяти семи раздачам настоящей части не соперник; а если живой
      картины рядом нет вовсе, претендент остаётся единственным, кого каталог назвал
      этим номером, - и честно показывается он.

    Без подписанных номеров с меньшим числом мерить не от чего: всякая безномерная
    картина (включая первую часть) оказалась бы «новее», и ответ уезжал бы на неё.
    """
    anchor = max(
        (p.year for p in line if p.part is not None and p.part < index and p.year is not None),
        default=None,
    )
    if anchor is None:
        return None
    newer = [
        p
        for p in items
        if p.kind != "other"
        and not p.collection
        and p.part is None
        and p.year is not None
        and p.year > anchor
    ]
    rival = max(newer, key=lambda p: len(p.releases), default=None)
    if rival is not None and len(rival.releases) > len(claimant.releases):
        return rival
    return None


#: Чем каталог вводит подзаголовок: двоеточием, а советское кино — словом «или».
_SUBTITLE_RE: Final = re.compile(r"\s*:\s*|,\s+или\s+")


def _by_subtitle(query: str, pictures: list[Picture]) -> list[Picture]:
    """Картины, чей ПОДЗАГОЛОВОК человек и назвал: «кольца власти» → «Властелин колец:
    Кольца власти».

    Каталог подписывает сериал полным именем («Властелин колец: Кольца власти»), а зовут
    его тем словом, под которым знают, — подзаголовком. В ключ франшизы подзаголовок не
    входит, его режет :func:`franchise_name` первым делом, и до этой проверки запрос
    «кольца власти» падал в пустоту при 39 раздачах до 117 сидов в первой же выдаче:
    ключа ``кольца-власти`` в каталоге нет, а ``властелин-колец`` в запрос не входит ни
    подстрокой, ни словами. Дальше пустоту добивал добор, приносивший по оригиналу
    ``The Lord of the Rings`` всю чужую франшизу, — и человек читал «ничего не нашлось».

    🔴 Отдаётся КАРТИНА с этим подзаголовком, а не её франшиза. Подзаголовком человек
    называет одну часть, и подставить вместо «Двух крепостей» всего «Властелина колец»
    значило бы молча показать другое кино.

    Подзаголовок сверяется ЦЕЛИКОМ, поэтому однофамильцы мимо: «кольца власти» — это не
    «Кольцо власти» 2007 года, лежащее в той же выдаче. Ищется и в русском имени, и в
    оригинале: половина каталога подписана только латиницей.
    """
    wanted = slugify(query)
    if not wanted:
        return []
    items = [p for p in pictures if wanted in _subtitles(p)]
    items.sort(key=lambda p: (p.year is None, p.year or 0, p.part or 99, -len(p.releases), p.title))
    return items


def _by_alias(query: str, pictures: list[Picture]) -> list[Picture]:
    """Картины, которых человек назвал ТРЕТЬИМ именем из их же заголовка.

    🔴 TC-244. Каталог подписывает картину перечислением имён, и знают её сплошь и рядом
    не первым из них: «Одна из многих / Из многих / **Плюрибус** / Pluribus» (10 строк),
    «Птицы 2 / **Марш пингвинов** / La marche de l'empereur» (5), «А в душе я танцую /
    **Внутри себя я танцую**» (13), «Каждый за себя / **Загадка Каспара Хаузера**» (1).
    Разбор читал первое имя и оригинал, а всё между ними терял - и запрос падал в пустоту
    при живых раздачах в своей же выдаче. Лишнего похода к индексерам тут нет: ответ уже
    приехал, его надо просто прочитать.

    🔴 **Псевдоним не вправе свести разные картины.** Одноимённость - больное место
    каталога («Призраки», «Ангел», «Убийство»), поэтому:

    * шаг последний: любое имя, которым каталог подписал картину сам, сильнее псевдонима,
      и до сюда доходит лишь то, что не нашлось никак иначе (:func:`pick_franchise`);
    * имя сверяется ЦЕЛИКОМ, без нестрогих ступеней с вхождением подстроки;
    * псевдоним, который тянет к себе больше одной франшизы, не решает ничего: молчим,
      как молчали, - честное «не нашлось» лучше однофамильца.
    """
    wanted = slugify(query)
    if not wanted:
        return []
    items = [p for p in pictures if wanted in p.aliases]
    if len({p.franchise for p in items}) != 1:
        return []
    items.sort(key=lambda p: (p.year is None, p.year or 0, p.part or 99, -len(p.releases), p.title))
    return items


def _by_both_names(query: str, pictures: list[Picture]) -> list[Picture]:
    """Картины, у которых в ДВУХ именах разом нашлись все слова запроса.

    Имя франшизы человек читает с обложки, а подзаголовок помнит по озвучке, и в запросе
    они встречаются в разных азбуках: «Gundam 0080 Карманная война» - это «Мобильный воин
    ГАНДАМ 0080: Карманная война», подписанная в каталоге ещё и оригиналом ``Mobile Suit
    Gundam 0080: War in the Pocket``. Ни одно из двух имён по отдельности всех слов запроса
    не содержит: «карманной войны» нет в оригинале, ``Gundam`` нет в русском написании
    («ГАНДАМ» - это ``gandam``, а не ``gundam``). Порознь их не сводит ничто, и запрос
    падал в пустоту.

    🔴 Отдаётся КАРТИНА, а не её франшиза - ровно по той же причине, что и в
    :func:`_by_subtitle`: слова подзаголовка человек назвал про одну часть, и подставить
    вместо неё всю линейку «Гандама» значило бы молча показать другое кино.

    Проверка тесная: слова сверяются ЦЕЛИКОМ (ни форм, ни начал), их должно быть хотя бы
    два, и найтись обязаны ВСЕ. Лишние слова в именах картины запросу не мешают - он
    короче полного имени всегда, - но своё слово каждый обязан предъявить.

    🔴 И главное: имена должны понадобиться ОБА. Хватило одного - эта ступень молчит, а
    отвечает лестница выше (ключи, оригиналы, подстроки, слова). Иначе шаг подменял бы
    собой всё, что уже умеет каталог: на корпусе в 418 картин без этого условия он один
    отвечал на восемь десятков запросов вместо штатных ступеней - и разбор имени начинал
    зависеть не от того, как картина подписана, а от того, чьи слова где встретились.
    """
    asked = _words(slugify(query))
    if len(asked) < 2:
        return []
    items = [p for p in pictures if asked <= _both_words(p) and not _one_name_is_enough(asked, p)]
    items.sort(key=lambda p: (p.year is None, p.year or 0, p.part or 99, -len(p.releases), p.title))
    return items


def _one_name_is_enough(asked: set[str], picture: Picture) -> bool:
    """Хватило ли одного имени картины, чтобы покрыть все слова запроса."""
    return any(asked <= _words(slugify(name)) for name in (picture.title, picture.original or ""))


def _both_words(picture: Picture) -> set[str]:
    """Все слова обоих имён картины: русского и оригинального."""
    return _words(slugify(picture.title)) | _words(slugify(picture.original or ""))


def _subtitles(picture: Picture) -> set[str]:
    """Подзаголовки картины — то, что каталог написал после двоеточия, слагами."""
    found = set()
    for title in (picture.title, picture.original or ""):
        parts = _SUBTITLE_RE.split(title.strip(), maxsplit=1)
        if len(parts) == 2 and (slug := slugify(parts[1])):
            found.add(slug)
    return found


def _kindred(picture: Picture, base: list[Picture]) -> bool:
    """Есть ли у картины с франшизой общее что-то, КРОМЕ слова в имени (TC-394).

    Мост между русским и оригинальным именем заведён ради находимости по обоим именам
    (см. :func:`_both_languages`), но слово - это всё, что он проверяет, а однофамильцев
    под одним словом у каталога полно: «whiplash» - это и сериал 1961 года на одну
    раздачу, и оригинал «Одержимости» 2014-го на шесть десятков. Свести их в одну
    франшизу значит отдать номер запроса сериалу («whiplash 2» читался вторым сезоном
    сериала, которого нет), тогда как человек звал картину.

    Общее - это тип картины или год (с тем же допуском ±1, что у гейта года в
    :func:`glue`): у двух половин ОДНОЙ картины, записанных на двух языках, совпадает
    хотя бы что-то из этого. Не совпало ничего - картины разные, и мост их не сводит.
    """
    for other in base:
        if picture.kind == other.kind:
            return True
        if picture.year is None or other.year is None or abs(picture.year - other.year) <= 1:
            return True
    return False


def _both_languages(
    groups: dict[str, list[Picture]], aliases: dict[str, str], key: str
) -> list[Picture]:
    """Франшиза целиком, когда её половина названа по-русски, а половина — латиницей.

    «Моана» на Knaben живёт двумя кучками: первая часть подписана только ``Moana``,
    вторая — ``Моана 2 / Moana 2``. Ключи франшиз у них разные (``moana`` и ``моана``),
    и запрос ``cast moana`` показывал бы только первую часть, а ``cast моана`` — только
    вторую. Псевдоним по оригинальному названию у нас уже посчитан — этого хватает,
    чтобы показать человеку всю франшизу, не трогая саму кластеризацию.

    🔴 TC-394. Близнецом становится не всякая франшиза под тем же словом, а та, у
    которой со спрошенной есть общее, кроме слова (:func:`_kindred`): тип или год.
    """
    items = list(groups[key])
    base = list(items)
    # Псевдоним считается от оригинального названия к русскому, а спросить могут любым:
    # ``cast moana`` и ``cast моана`` обязаны показать одну и ту же франшизу.
    twins = {aliases.get(key, "")} | {a for a, target in aliases.items() if target == key}
    seen = {id(p) for p in items}
    for twin in twins:
        if not twin or twin == key:
            continue
        # ⚠️ В `seen` уходят только новички: пересчёт по всему списку стоил бы прохода на
        # каждого близнеца, то есть квадрата по числу картин на ровном месте.
        # Родство меряется со спрошенной франшизой, а не с уже принятыми близнецами:
        # иначе цепочка «у каждого звена что-то общее с соседом» стянула бы в одну
        # франшизу и чужие картины.
        fresh = [p for p in groups.get(twin, []) if id(p) not in seen and _kindred(p, base)]
        items += fresh
        seen |= {id(p) for p in fresh}
    items.sort(key=lambda p: (p.year is None, p.year or 0, p.part or 99, -len(p.releases), p.title))
    return items


def _normalize(name: str) -> str:
    # «№» снимается до NFKC, иначе он станет буквами «No» и прирастёт к числу
    # (:data:`_NUMERO_RE`): и в ключе, и в имени картины на экране.
    text = unicodedata.normalize("NFKC", _NUMERO_RE.sub(" ", name)).replace("\xa0", " ")
    text = text.replace("–", "-").replace("—", "-").replace("‐", "-")
    text = re.sub(r"(\d{3,4})\s*р\b", r"\1p", text)  # 720р (кириллица) → 720p
    return re.sub(r"\s+", " ", text).strip()


def _find_year(text: str) -> tuple[int | None, tuple[int, int] | None]:
    for pattern in _YEAR_PATTERNS:
        match = pattern.search(text)
        if match:
            return int(match.group(1)), match.span()
    return None, None


def _fansub_episode(text: str) -> re.Match[str] | None:
    """Совпадение ``[Группа] Название - 12 [...]`` или ``None``; год в имени запрещает.

    Одна точка правды для двух читателей: :func:`_title_zone` берёт отсюда НАЗВАНИЕ (без
    номера), :func:`_parse_series` - НОМЕР СЕРИИ. Разъедься они - и номер остался бы в
    названии, а кластер по-прежнему заводил бы под каждую серию свою «картину».
    """
    if _find_year(text)[0] is not None:
        return None
    return _FANSUB_EPISODE_RE.match(text)


def _title_zone(text: str, span: tuple[int, int] | None) -> tuple[str, bool]:
    """Отрезать от имени кусок, в котором лежат названия; вторым - сборник ли это.

    Сборник узнаётся ровно тем словом, по которому имя и обрезано
    (:data:`_COLLECTION_CUT_RE`): «Хоббит: **Трилогия** / The Hobbit: Trilogy», «Гарри
    Поттер: **Коллекция**». Второго разбора имени под это нет и не нужно - вопрос «где
    кончилось название» и вопрос «сборник ли это» решает одна и та же находка.
    """
    # Номер серии - не часть имени. Без этого «Gintama: 3-nen Z-gumi Ginpachi-sensei - 11»
    # и «- 12» становились РАЗНЫМИ картинами, каждая в пару раздач, и дефолт садился на
    # такой огрызок при полном каталоге рядом (TC-151). Зона при этом идёт дальше по
    # общему пути: «Haikyuu!! 2nd Season» обязана обрезаться там же, где обрезалась.
    fansub = _fansub_episode(text)
    zone = fansub.group("name") if fansub else (text[: span[0]] if span else text)
    # Скобки убираем ПЕРВЫМИ: иначе «сезон» внутри «(5 сезон: 1-3 серии из 3)»
    # обрежет строку раньше оригинального названия, которое идёт после скобки.
    zone = _BRACKETS_RE.sub(" ", zone)  # (Режиссёр), [S01], (IMAX Edition), [Group]
    cut = _TITLE_CUT_RE.search(zone)
    collection = bool(cut and _COLLECTION_CUT_RE.match(cut.group(0)))
    if cut:
        tail = zone[cut.end() :].lstrip()
        if cut.group(0).casefold() in _RU_CUT_WORDS and tail[:1] in ("/", "|"):
            # 🔴 TC-282. Метка сборника закрывает только СВОЙ кусок: «Матрица: Трилогия /
            # The Matrix: Trilogy». Рез по ней уносил и оригинал за слэшем - картина
            # оставалась без оригинального названия вовсе. Метка режется, а кусок за
            # слэшем живёт дальше; техтокены в нём режутся тем же правилом.
            rest = _TITLE_CUT_RE.search(tail)
            zone = zone[: cut.start()] + (tail[: rest.start()] if rest else tail)
        else:
            zone = zone[: cut.start()]
    zone = _OPEN_BRACKET_RE.split(zone)[0]  # обрезали внутри скобки: «Bleach ... [»
    # Отдельного правила для «от <релиз-группа>» нет и быть не должно: «от» -
    # обычный предлог («Человек-паук: Вдали от дома»), а хвост с группой и так
    # остаётся за техническим токеном, по которому строка уже обрезана.
    if zone.count(".") >= 2 and zone.count(" ") <= 1:  # scene-имя через точки
        zone = zone.replace(".", " ")
    zone = _TITLE_TAIL_RE.sub("", zone)
    return zone.strip(" .-_|,:;/"), collection


def _split_titles(zone: str) -> tuple[str, str | None, tuple[str, ...]]:
    """``«Матрица / The Matrix»`` → русское название, оригинал и всё, что между ними.

    🔴 TC-244. Третье имя в заголовке раздачи - не украшение, а единственное имя, под
    которым картину знают: «Одна из многих / Из многих / Плюрибус / Pluribus», «Птицы 2 /
    Марш пингвинов / La marche de l'empereur», «А в душе я танцую / Внутри себя я танцую».
    Читались только первое имя и оригинал, всё между ними терялось - и запрос «плюрибус»
    падал в пустоту при десяти строках этой самой раздачи в своей же выдаче.

    Отдаём такие имена третьим полем, а не подменяем ими первое: каноническое имя картины
    по-прежнему считает каталог большинством (:func:`_compose`), и подмены имени в меню
    тут нет. Псевдонимом ищут - и только (:func:`_by_alias`).

    Зона имён приходит уже обрезанной (:func:`_title_zone`): всё после первой скобки и
    после первого технического токена в неё не входит, так что перечислением имён считается
    ровно заголовок, а не хвост раздачи.
    """
    parts = [p.strip(" .-_|,:;") for p in re.split(r"[/|]", zone)]
    numeric_original = (
        len(parts) == 2 and bool(_CYRILLIC.search(parts[0])) and bool(re.fullmatch(r"\d", parts[1]))
    )
    # Односимвольное число бывает полным оригинальным именем картины: «Девять / 9».
    # Буквенные односимвольные куски остаются служебными метками и именем не становятся.
    parts = [
        p
        for p in parts
        if (len(p) > 1 or (numeric_original and p.isdigit())) and not _TAG_ONLY_RE.match(p)
    ]
    if not parts:
        return zone.strip() or "?", None, ()

    russian = next((p for p in parts if _CYRILLIC.search(p) and not _UKRAINIAN.search(p)), None)
    latin = next(
        (p for p in parts if (p.isdigit() or _LATIN.search(p)) and not _CYRILLIC.search(p)),
        None,
    )
    if russian is None:
        return latin or parts[0], None, ()
    return russian, latin, tuple(p for p in parts if p != russian and p != latin)


def _parse_codec(text: str) -> str | None:
    """Кодек из имени. ⚠️ H.264 проверяется раньше MPEG-4: «MPEG-4 AVC» — это H.264,
    так пишут на rutracker про BDRip-AVC, и без этого порядка годный релиз уехал бы
    в старьё.
    """
    if _HEVC_RE.search(text):
        return "HEVC"
    if _H264_RE.search(text):
        return "H.264"
    if _MPEG4_RE.search(text):
        return "MPEG-4"
    return "AV1" if _AV1_RE.search(text) else None


def _parse_source(text: str) -> str | None:
    for pattern, label in _SOURCES:
        if re.search(pattern, text, re.IGNORECASE):
            return label
    return None


def _parse_voices(text: str) -> tuple[str, ...]:
    """Собрать маркеры озвучки в порядке приоритета, без повторов."""
    found: list[str] = []
    for pattern, label in _VOICES:
        if re.search(pattern, text, re.IGNORECASE) and label not in found:
            found.append(label)
    for segment in re.split(r"[|/]", text)[1:]:  # хвост rutor/megapeer: «| D, P, A»
        if not _TAG_ONLY_RE.match(segment):
            continue
        for code in re.findall(r"[DPAL]2?", segment):
            label = _TAG_VOICES.get(code) or _TAG_VOICES[code[0]]
            if label not in found:
                found.append(label)
    order = {label: i for i, (_, label) in enumerate(_VOICES)}
    return tuple(sorted(found, key=lambda v: order.get(v, 99)))


def _parse_series(
    text: str,
) -> tuple[int | None, int | None, tuple[int, ...], tuple[int, ...], bool]:
    """Сезон, серия, сезоны пака, серии пака и признак сериальности.

    ⚠️ Перед разбором из имени вырезаются токены кодека (:data:`_CODEC_TOKEN_RE`). Иначе
    ``x264`` рядом с любой цифрой читается как ``NxM``: «Moana 2 2024 … DDP5 1 x264» —
    это «5.1» плюс кодек, а разбор видел «1 x264» и объявлял полнометражку сериалом
    s1e264. Кодек о сериях не говорит ничего, поэтому вырезать его здесь безопасно —
    а весь остальной парсер остаётся как был.

    Фансабовский номер (:data:`_FANSUB_EPISODE_RE`) читается ПОСЛЕДНИМ из номеров и до
    вырезания кодека: он привязан к началу имени, где кодека нет и быть не может. Ниже
    ``SxxExx`` и диапазонов он стоит потому, что те точнее — они называют ещё и сезон.
    """
    fansub = _fansub_episode(text)
    text = _CODEC_TOKEN_RE.sub(" ", text)
    seasons = _season_span(text)
    episodes = _episode_span(text)
    if seasons:
        # Диапазон сезонов задаёт покрытие, а отдельный E-диапазон считает серии
        # всего пака. Голый «S01-15» сериями не становится.
        return seasons[0], None, seasons, episodes, True
    found = parse_episode(text)
    if found is not None:
        # «S2E1-8 of 8» - это пак сезона, а не первая серия.
        pack = re.search(r"[eхx]\s*\d{1,3}\s*-\s*\d{1,3}", text, re.IGNORECASE)
        # В полном паке S1 - начало сквозной нумерации, а диапазон лет
        # подтверждает, что серии выходили дольше одного сезона.
        years = [int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", text)]
        linear = bool(
            pack
            and found.season == 1
            and len(episodes) > 24
            and years
            and max(years) - min(years) >= 2
        )
        return None if linear else found.season, None if pack else found.episode, (), episodes, True
    number = int(fansub.group("episode")) if fansub else None
    for pattern in _SEASON_ONLY_RES:
        match = pattern.search(text)
        if match:
            return int(match.group("season")), number, (), episodes, True
    if number is not None:
        # Сезон в фансабовском имени называют не всегда («Haikyuu!! - 03»); молчание о
        # сезоне у релиза значит «может быть любой» (:meth:`Release.covers`), а вот номер
        # серии теперь честный - и огрызок больше не выдаёт себя за весь сериал.
        return None, number, (), episodes, True
    # Перечисленные серии - сами по себе признак сериала: имя, назвавшее диапазон серий,
    # о сериальности уже сказало («[01-201]»), и ждать от него ещё и слова «сезон»
    # значило бы записать сквозную нумерацию в фильмы (TC-169).
    return None, None, (), episodes, bool(episodes) or bool(_SERIES_HINT_RE.search(text))


def _episode_span(text: str) -> tuple[int, ...]:
    """Серии внутри раздачи по имени: «1-5 из 220» → (1…5), «220 of 220» → (1…220).

    Пусто — имя о серияx молчит. Диапазон читается раньше счёта (:data:`_EPISODE_SPAN_RES`
    против :data:`_EPISODE_COUNT_RE`), иначе «1-5 из 220» дало бы «серии 1…1»: «5 из 220»
    прочиталось бы как счёт. Вывернутые и бессмысленные границы («8-1», «0-500»)
    отбрасываются молча — врать в обе стороны хуже, чем промолчать.
    """
    for pattern in _EPISODE_SPAN_RES:
        match = pattern.search(text)
        if match:
            start, end = int(match.group("start")), int(match.group("end"))
            if 1 <= start <= end:
                return tuple(range(start, end + 1))
    match = _EPISODE_COUNT_RE.search(text)
    if match:
        count, total = int(match.group("count")), int(match.group("total"))
        if 1 <= count <= total:
            return tuple(range(1, count + 1))
    return ()


def _season_span(text: str) -> tuple[int, ...]:
    """Диапазон сезонов из имени раздачи: ``[S01-06]``, «1-6 сезоны» → (1…6)."""
    for pattern in _SEASON_SPAN_RES:
        match = pattern.search(text)
        if match:
            first, last = int(match.group(1)), int(match.group(2))
            if 0 < first < last <= 40:
                return tuple(range(first, last + 1))
    return ()


def _is_non_video(text: str) -> bool:
    """Музыка/книги/игры: не-видео маркеры при полном отсутствии видео-маркеров."""
    return bool(_NON_VIDEO_RE.search(text)) and not _VIDEO_MARKER_RE.search(text)


def _normalize_quality(value: str) -> str:
    lowered = value.lower()
    return "2160p" if lowered in {"4k", "uhd"} else lowered
