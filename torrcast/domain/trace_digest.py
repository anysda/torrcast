"""Разбор ленты следа в человеческий текст: чем кончился сеанс и что в нём было.

Чистое чтение записей: ни файлов, ни очереди - их держит сам след
(:mod:`torrcast.adapters.filesystem.trace_journal`). Зовёт разбор ``cast log``.
"""

from __future__ import annotations

import time
from typing import Any, Final

from torrcast.domain.trace_sources import PACKED, WARMED

#: Что считается в итоговой строке сеанса и как это называется по-русски. Ребуферы
#: печатаются всегда (ноль ребуферов - тоже новость), остальное - только когда было.
_COUNTED: Final = {
    "buffering": "ребуферов",
    "offline": "обрывов сети",
    "resupply": "возвратов раздачи магнитом",
    "dark": "погасаний показа",
    "revive": "воскрешений показа",
    "nudge": "нуджей сторожа",
    "reload": "повторов LOAD",
    "seek": "перемоток",
    "evict": "вытеснений прогрева",
    "skew": "кусков мимо сетки",
}

#: Решение о кодировании куска по-русски (:func:`plan`).
_PLAN: Final = {"copy": "копия", "recode": "перекод"}

#: Как называется источник куска в выжимке.
_SOURCES: Final = {PACKED: "живая упаковка", WARMED: "прогретое"}

#: Конверт записи (:func:`emit`): он одинаков у всех и в строке события не печатается.
_ENVELOPE: Final = frozenset({"at", "sid", "pid", "phase", "event"})


def _hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _clock(at: float) -> str:
    return time.strftime("%d.%m %H:%M", time.localtime(at))


def digest(rows: list[dict[str, Any]], limit: int = 3) -> str:
    """Читаемая выжимка последних сеансов: что искали, что взяли, ребуферы и ошибки.

    Сеанс - все записи с одним ``sid``. Каждая серия начинает новый идентификатор через
    :func:`start_session`. Порядок - от свежих; ``limit`` ограничивает число сеансов,
    ``0`` - все.
    """
    if not rows:
        return "следа нет - за неделю ни одного сеанса"
    order: list[str] = []
    by_sid: dict[str, list[dict[str, Any]]] = {}
    for rec in rows:
        sid = str(rec.get("sid", "?"))
        if sid not in by_sid:
            by_sid[sid] = []
            order.append(sid)
    for rec in rows:
        by_sid[str(rec.get("sid", "?"))].append(rec)
    order.sort(key=lambda s: float(by_sid[s][-1].get("at", 0.0)), reverse=True)
    if limit > 0:
        order = order[:limit]
    blocks = [_session_block(sid, by_sid[sid]) for sid in order]
    return "\n\n".join(blocks)


def _seams(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Записи сегментов, на которых сменился источник (:func:`segment`).

    Первый кусок сеанса стыком не считается: у него нет предыдущего источника, а «показ
    начался с прогретого» - не стык, а начало. Пустой список значит ровно «в ленте нет
    записей с полем ``src``» ИЛИ «источник за весь сеанс не менялся»: эти два случая
    различаются наличием самих записей сегментов, и путать их нельзя.
    """
    found: list[dict[str, Any]] = []
    previous = ""
    for rec in rows:
        if rec.get("event") != "segment":
            continue
        src = str(rec.get("src", ""))
        if not src:
            continue
        if previous and src != previous:
            found.append(rec)
        previous = src
    return found


def _session_block(sid: str, rows: list[dict[str, Any]]) -> str:
    began = float(rows[0].get("at", 0.0))
    lines: list[str] = []
    query = next((r for r in rows if r.get("event") == "query"), None)
    title = query.get("query") if query else None
    head = f"сеанс {sid} · {_clock(began)}"
    if title:
        head += f" · «{title}»"
    lines.append(head)
    seams = {id(rec) for rec in _seams(rows)}
    # Фаза таймлайна повторяется: упаковка заходит на каждый прыжок, тяжёлый кусок - на
    # каждый слот. Печатается ПЕРВАЯ и сказано, сколько их было всего, - иначе одна фаза
    # съедает выжимку так же, как её съели бы куски (:func:`_event_line`, ветка segment).
    phases: dict[str, int] = {}
    for rec in rows:
        if rec.get("phase") == "timeline":
            name = str(rec.get("event", ""))
            phases[name] = phases.get(name, 0) + 1
    shown: set[str] = set()
    for rec in rows:
        name = str(rec.get("event", ""))
        if rec.get("phase") == "timeline":
            if name in shown:
                continue
            shown.add(name)
        line = _event_line(rec, began, seam=id(rec) in seams)
        if not line:
            continue
        if phases.get(name, 1) > 1 and rec.get("phase") == "timeline":
            line += f", всего {phases[name]}"
        lines.append("  " + line)
    counts = {name: sum(1 for r in rows if r.get("event") == name) for name in _COUNTED}
    tail = f"  итог: ребуферов {counts['buffering']}"
    if seams:
        tail += f", стыков источника {len(seams)}"
    for name, word in _COUNTED.items():
        if name != "buffering" and counts[name]:
            tail += f", {word} {counts[name]}"
    end = next((r for r in reversed(rows) if r.get("event") == "session_end"), None)
    if end is not None:
        where = _hms(float(end.get("pos", 0.0)))
        dur = float(end.get("dur", 0.0))
        watched = end.get("watched")
        state = "досмотрено" if watched else f"остановлено на {where}"
        tail += f"; {state}" + (f" из {_hms(dur)}" if dur and not watched else "")
    lines.append(tail)
    return "\n".join(lines)


def _gb(size: float) -> str:
    return f"{size / 1e9:.1f} ГБ"


def _facts(rec: dict[str, Any]) -> str:
    """Поля записи как есть, ``имя=значение``: чем печатать событие, у которого нет ветки.

    Для фазы таймлайна это не запасной вариант, а единственно верный: числа у неё разные
    у каждой метки (``слот=7 сдвиг=-1.71``), и знает их место вызова, а не этот модуль.
    """
    facts = ", ".join(f"{key}={value}" for key, value in rec.items() if key not in _ENVELOPE)
    return f" ({facts})" if facts else ""


def _event_line(rec: dict[str, Any], began: float, seam: bool = False) -> str:
    at = float(rec.get("at", 0.0)) - began
    stamp = f"+{at:6.1f}с "
    event = rec.get("event", "")
    if event == "segment":
        # Каждый кусок в выжимку не печатаем - их сотни; печатаем только смену источника.
        if not seam:
            return ""
        src = str(rec.get("src", ""))
        return f"{stamp}v{rec.get('slot', '?')}: источник сменился на {_SOURCES.get(src, src)}"
    if event == "plan":
        spots = int(rec.get("spots", 0))
        tail = f", точечный перекод {spots}" if spots else ""
        return (
            f"{stamp}куски: упаковка - {_PLAN.get(str(rec.get('pack', '')), '?')},"
            f" прогрев - {_PLAN.get(str(rec.get('warm', '')), '?')}{tail}"
        )
    if event == "indexers":
        got = rec.get("got") or {}
        silent = rec.get("silent") or []
        took = rec.get("ms") or {}

        def _took(name: object) -> str:
            # Время держим за именем: «за 0.4 с» после счётчика, у молчунов - вместо него.
            # В записях прежних версий поля ms нет вовсе - тогда строка выглядит как раньше.
            ms = took.get(str(name)) if isinstance(took, dict) else None
            return f" за {float(ms) / 1000:.1f} с" if ms is not None else ""

        parts = ", ".join(f"{name}:{count}{_took(name)}" for name, count in got.items())
        tail = f"; молчат {', '.join(str(name) + _took(name) for name in silent)}" if silent else ""
        # Опоздавшие - не молчуны: круг ушёл по кворуму, а они доезжают доливом (TC-118).
        # Разница видна только тут, и без неё выжимка врала бы про причину хвоста.
        waited = rec.get("late") or []
        if waited:
            tail += f"; опоздали {', '.join(str(name) for name in waited)}"
        return f"{stamp}индексеры {parts or '-'}{tail}"
    if event == "query":
        # Запрос печатался только в шапке сеанса («сеанс ... · «Сталкер»»), а сколько
        # строк и картин он принёс - нигде: у события не было своей ветки, и оно молча
        # выпадало из ленты. В записях прежних версий полей может не быть - молчим о них.
        raw, pictures = rec.get("raw"), rec.get("pictures")
        tail = f": строк {raw}" if raw is not None else ""
        tail += f", картин {pictures}" if pictures is not None else ""
        return f"{stamp}запрос «{rec.get('query', '')}»{tail}"
    if event == "select":
        return (
            f"{stamp}взят релиз {rec.get('release', '?')}"
            f" · {rec.get('quality', '?')} · {rec.get('track', '?')}"
            f" · ~{rec.get('mbit', '?')} Мбит/с"
        )
    if event == "queue":
        # Отсев до очереди - свёрткой, а не событием на раздачу: их сотни на запрос.
        # Сумма очереди и причин обязана сходиться с пулом, и в строке это видно глазами.
        dropped = rec.get("dropped") or {}
        reasons = ", ".join(f"{name} {count}" for name, count in dropped.items())
        lost = sum(int(count) for count in dropped.values())
        head = f"{stamp}пул {rec.get('pool', '?')}: в очереди {rec.get('queued', '?')}"
        return f"{head}, выкинуто {lost}" + (f" ({reasons})" if reasons else "")
    if event == "runtime":
        # Знаменатель битрейта отбора: чем считали и откуда взяли (TC-185).
        got = "из справки" if rec.get("src") == "facts" else "прикидка: справка молчит"
        return f"{stamp}длительность {_hms(float(rec.get('secs', 0.0)))} - {got}"
    if event == "drop":
        return f"{stamp}отброшен релиз {rec.get('release', '?')}: {rec.get('why', '?')}"
    if event == "mute":
        # 🔴 TC-178. Русской озвучки не нашлось ни у одного проверенного кандидата, и
        # показ пошёл запасным ходом. Это дыра КАТАЛОГА, а не осечка отбора: по этим
        # записям замер и считает, у скольких картин русской дорожки нет вовсе.
        return (
            f"{stamp}русской озвучки нет ни у кого (проверено {rec.get('checked', '?')})"
            f" - играю релиз {rec.get('release', '?')}, звук {rec.get('lang', '?')}"
        )
    if event == "switch":
        # Смена КАРТИНЫ посреди отбора (TC-203): у выбранной играть нечем, рядом живёт
        # одноимённая живая. Решение это громкое, и в ленте оно обязано быть видно так же,
        # как на экране, - иначе разбор отказа не сойдётся с тем, что человек читал.
        return (
            f"{stamp}у «{rec.get('from', '?')}» играть нечем ({rec.get('why', '?')})"
            f" - ухожу к «{rec.get('to', '?')}»"
        )
    if event == "note":
        return f"{stamp}{rec.get('text', '')}"
    if event == "buffering":
        return f"{stamp}ребуфер на {_hms(float(rec.get('pos', 0.0)))}"
    if event == "offline":
        # Спрошенный источник называется источником: «сеть» тут была бы догадкой, а мы
        # знаем точно - служба ответила (или не ответила) нам сама.
        head = "источник" if rec.get("asked") else "сеть"
        return f"{stamp}{head}: {rec.get('why', 'обрыв')}"
    if event == "resupply":
        end = "раздача вернулась" if rec.get("ok") else "служба ещё не отдала раздачу"
        return f"{stamp}раздачу добавил магнитом заново - {end}"
    if event == "nudge":
        return (
            f"{stamp}нудж сторожа {rec.get('hit', 1)}:"
            f" {_hms(float(rec.get('pos', 0.0)))} -> {_hms(float(rec.get('to', 0.0)))}"
            f" (стоял {float(rec.get('stuck', 0.0)):.0f} с,"
            f" готово впереди {float(rec.get('front', 0.0)) - float(rec.get('pos', 0.0)):.0f} с)"
        )
    if event == "reload":
        error = ""
        if "error" in rec:
            error = f", код {rec['error']}" if rec.get("error") is not None else ", без кода"
        return (
            f"{stamp}приёмник отвалился на {_hms(float(rec.get('pos', 0.0)))}"
            f"{error} - повтор LOAD {rec.get('tries', 1)}"
        )
    if event == "dark":
        return (
            f"{stamp}показ погас на {_hms(float(rec.get('pos', 0.0)))}:"
            f" {rec.get('why', 'приёмник бросил показ')}"
        )
    if event == "revive":
        took = "показ поднят" if rec.get("ok") else "приёмник показ не взял"
        return (
            f"{stamp}{took} с {_hms(float(rec.get('pos', 0.0)))}"
            f" (попытка {rec.get('tries', 1)},"
            f" темнота {float(rec.get('waited', 0.0)):.0f} с)"
        )
    if event == "seek":
        wait = rec.get("wait")
        # Картинки не было вовсе - это отдельный исход, а не нулевое ожидание: нулём его
        # печатала как раз старая метрика, верившая слову приёмника.
        back = (
            f" картинка через {float(wait):.1f} с"
            if wait is not None
            else f" картинки так и не было: {rec.get('why', 'причина не названа')}"
        )
        return (
            f"{stamp}перемотка {_hms(float(rec.get('frm', 0.0)))}"
            f" -> {_hms(float(rec.get('to', 0.0)))},{back}"
        )
    if event == "evict":
        who = rec.get("title") or rec.get("key", "?")
        return (
            f"{stamp}бюджет прогрева вытеснил «{who}»:"
            f" освободилось {_gb(float(rec.get('freed', 0.0)))}"
            f" под {_gb(float(rec.get('need', 0.0)))}"
        )
    if event == "skew":
        end = "место осталось непрогретым" if rec.get("hole") else "кусок переложен заново"
        return (
            f"{stamp}v{rec.get('slot', '?')} лёг мимо сетки:"
            f" начало {float(rec.get('off', 0.0)):+.2f} с"
            f" от границы {_hms(float(rec.get('want', 0.0)))} - {end}"
        )
    if event in {"ready", "stall"}:
        head = (
            f"{stamp}прогрето {_hms(float(rec.get('secs', 0.0)))}"
            f" из {_hms(float(rec.get('dur', 0.0)))}"
            f" ({float(rec.get('share', 0.0)) * 100:.0f} %,"
            f" {_gb(float(rec.get('size', 0.0)))})"
        )
        why = rec.get("why")
        return f"{head} - прогрев встал: {why}" if why else head
    if event == "error":
        return f"{stamp}ошибка: {rec.get('text', '')}"
    if event == "session_start":
        # Профиль приёмника: по какому набору порогов играли. В записях прежних версий
        # его нет вовсе - тогда и в строке о нём молчим, а не пишем «профиль ?».
        profile = str(rec.get("profile", ""))
        head = f"{stamp}показ «{rec.get('title', '')}» с {_hms(float(rec.get('pos', 0.0)))}"
        if not profile:
            return head
        source = str(rec.get("profile_source", ""))
        thresholds = rec.get("thresholds", {})
        origins = rec.get("threshold_sources", {})
        profile_text = f" · профиль {profile}" + (f" ({source})" if source else "")
        if not isinstance(thresholds, dict) or not thresholds:
            return f"{head}{profile_text}"
        origins = origins if isinstance(origins, dict) else {}
        details = ", ".join(
            f"{key}={value} [{origins.get(key, '?')}]" for key, value in thresholds.items()
        )
        return f"{head}{profile_text} · пороги: {details}"
    if event == "session_end":
        return ""  # конец сеанса печатает итоговая строка блока, второй раз незачем
    if event == "lost":
        return (
            f"{stamp}потеряно записей {rec.get('count', '?')}:"
            " очередь следа переполнилась - этих решений в ленте нет"
        )
    if str(rec.get("phase", "")) == "timeline":
        # Фазы критического пути (:func:`torrcast.timing.mark`) уходят в ленту ВСЕГДА, а до
        # TC-194 не печатались НИКОГДА: своей ветки у них нет, и они выпадали в общий
        # «вернуть пусто» - целый класс событий, которого человек в `cast log` не видел,
        # хотя в jsonl он лежит. Имя фазы и её числа уже по-русски («отбор релиза
        # релиз=2»), поэтому печатаются как есть.
        return f"{stamp}фаза «{event}»{_facts(rec)}"
    # Событие, о котором ЭТА версия не знает: чужая ветка, старая лента, новое поле.
    # Молчать о нём нельзя ровно по той же причине: пустая строка в выжимке читается как
    # «события не было», а оно было и лежит в файле.
    return f"{stamp}{rec.get('phase', '?')}/{event}{_facts(rec)}"
