"""Русские надписи кластера выжимки следа."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера выжимки следа.

    Ключа, которого тут нет, продукт скажет по-английски
    (:func:`torrcast.domain.catalogs.phrase.phrase`): русский каталог - надстройка над
    английским, а не второй полный словарь, который обязан поспевать за первым.
    """
    return {
        # Общее: отметка времени, вес, пустая лента.
        "digest.stamp": "+{at}с ",
        "digest.gb": "{size} ГБ",
        "digest.no_trace": "следа нет - за неделю ни одного сеанса",
        "digest.phase": "{stamp}фаза «{event}»{facts}",
        # Сеанс: ошибка, начало с порогами, потери ленты.
        "digest.error": "{stamp}ошибка: {text}",
        "digest.lost": (
            "{stamp}потеряно записей {count}:"
            " очередь следа переполнилась - этих решений в ленте нет"
        ),
        "digest.show_start": "{stamp}показ «{title}» с {pos}",
        "digest.profile": " · профиль {profile}",
        "digest.thresholds": "{head}{profile} · пороги:\n    {details}",
        # Поиск и отбор.
        "digest.indexers": "{stamp}индексеры {parts}{tail}",
        "digest.took": " за {secs} с",
        "digest.silent": "; молчат {names}",
        "digest.late": "; опоздали {names}",
        "digest.query": "{stamp}запрос «{query}»{tail}",
        "digest.query_rows": ": строк {raw}",
        "digest.query_pictures": ", картин {pictures}",
        "digest.select": "{stamp}взят релиз {release} · {quality} · {track} · ~{mbit} Мбит/с",
        "digest.queue": "{stamp}пул {pool}: в очереди {queued}, выкинуто {lost}",
        "digest.runtime": "{stamp}длительность {secs} - {got}",
        "digest.runtime_facts": "из справки",
        "digest.runtime_guess": "прикидка: справка молчит",
        "digest.drop": "{stamp}отброшен релиз {release}: {why}",
        "digest.mute": (
            "{stamp}русской озвучки нет ни у кого (проверено {checked})"
            " - играю релиз {release}, звук {lang}"
        ),
        "digest.switch": "{stamp}у «{frm}» играть нечем ({why}) - ухожу к «{to}»",
        # Прогрев.
        "digest.warm_off": (
            "{stamp}прогрев выключен настройкой, поэтому в этом прогоне его событий не будет"
        ),
        "digest.evict": "{stamp}бюджет прогрева вытеснил «{who}»: освободилось {freed} под {need}",
        "digest.skew": ("{stamp}v{slot} лёг мимо сетки: начало {off} с от границы {want} - {end}"),
        "digest.skew_hole": "место осталось непрогретым",
        "digest.skew_redone": "кусок переложен заново",
        "digest.warmed": "{stamp}прогрето {secs} из {dur} ({share} %, {size})",
        "digest.warm_stalled": "{head} - прогрев встал: {why}",
        # Показ: куски и план кодирования.
        "digest.plan_copy": "копия",
        "digest.plan_recode": "перекод",
        "digest.plan_splice": "склейка",
        "digest.plan_shrink": "ужатие",
        "digest.src_packed": "живая упаковка",
        "digest.src_warmed": "прогретое",
        "digest.src_warmed_copy": "прогретую копию",
        "digest.src_warmed_recode": "прогретый перекод",
        "digest.seam": "{stamp}v{slot}: источник сменился на {src}",
        "digest.plan_spots": ", точечный перекод: {named}",
        "digest.plan_spot_count": ", точечный перекод {count}",
        "digest.plan": "{stamp}куски: упаковка - {pack}, прогрев - {warm}{tail}",
        # Показ: всё, что мешало играть.
        "digest.buffering": "{stamp}ребуфер на {pos}",
        "digest.freeze": (
            "{stamp}подгруз на {pos}: потеряно {lost} с за {secs} с"
            " ({state}, готово впереди {front} с), за показ {total} с"
        ),
        "digest.offline_source": "источник",
        "digest.offline_net": "сеть",
        "digest.offline_why": "обрыв",
        "digest.offline": "{stamp}{head}: {why}",
        "digest.resupply_ok": "раздача вернулась",
        "digest.resupply_wait": "служба ещё не отдала раздачу",
        "digest.resupply": "{stamp}раздачу добавил магнитом заново - {end}",
        "digest.nudge": (
            "{stamp}нудж сторожа {hit}: {pos} -> {to} (стоял {stuck} с, готово впереди {front} с)"
        ),
        "digest.reload_code": ", код {error}",
        "digest.reload_no_code": ", без кода",
        "digest.reload": "{stamp}приёмник отвалился на {pos}{error} - повтор LOAD {tries}{end}",
        "digest.reload_failed": " - не вышло: {why}",
        "digest.refetch_failed": " - не вышло: {why}",
        "digest.why_unnamed": "причина не названа",
        "digest.refetch": "{stamp}перезабор куска на {pos} (попытка {tries}){end}",
        "digest.dark_at": "показ погас на {pos}",
        "digest.dark_blank": "показ не дал ни кадра",
        "digest.dark_why": "приёмник бросил показ",
        "digest.dark": "{stamp}{head}: {why}",
        "digest.revive_ok": "показ поднят",
        "digest.revive_failed": "приёмник показ не взял",
        "digest.revive": "{stamp}{took} с {pos} (попытка {tries}, темнота {waited} с)",
        "digest.seek_shown": " картинка через {wait} с",
        "digest.seek_blank": " картинки так и не было: {why}",
        "digest.seek": "{stamp}перемотка {frm} -> {to},{back}",
        # Блок сеанса: шапка и итоговая строка.
        "digest.session_head": "сеанс {sid} · {clock}",
        "digest.session_title": " · «{title}»",
        "digest.phase_total": ", всего {count}",
        "digest.total": "итог: ребуферов {count}",
        "digest.total_seams": ", стыков источника {count}",
        "digest.total_shrunk": (
            ", ужатий {shrunk}, склейка ужатого: попыток {tried}, удач {won}, без попытки {skipped}"
        ),
        "digest.watched": "досмотрено",
        "digest.stopped_at": "остановлено на {where}",
        "digest.end_of": " из {dur}",
        # Счётчики итоговой строки: слово на событие.
        "digest.count_buffering": "ребуферов",
        "digest.count_offline": "обрывов сети",
        "digest.count_resupply": "возвратов раздачи магнитом",
        "digest.count_dark": "погасаний показа",
        "digest.count_revive": "воскрешений показа",
        "digest.count_nudge": "нуджей сторожа",
        "digest.count_reload": "повторов LOAD",
        "digest.count_refetch": "перезаборов куска",
        "digest.count_seek": "перемоток",
        "digest.count_evict": "вытеснений прогрева",
        "digest.count_skew": "кусков мимо сетки",
    }
