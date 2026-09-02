"""Кого включит Enter: единственная ступень, отвечающая на этот вопрос."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice.absent_first_part import absent_first_part
from torrcast.usecases.choice.absent_part_line import absent_part_line
from torrcast.usecases.choice.certain_default import certain_default
from torrcast.usecases.choice.default_line import default_line
from torrcast.usecases.choice.default_taken_line import default_taken_line
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.choice.lone_other_part import lone_other_part
from torrcast.usecases.choice.lone_other_part_taken_line import lone_other_part_taken_line
from torrcast.usecases.choice.named_elsewhere import named_elsewhere
from torrcast.usecases.choice.named_take import named_take
from torrcast.usecases.choice.named_taken_line import named_taken_line
from torrcast.usecases.choice.namesake_line import namesake_line
from torrcast.usecases.choice.namesake_take import namesake_take
from torrcast.usecases.choice.part_one_swap import part_one_swap
from torrcast.usecases.choice.part_one_taken_line import part_one_taken_line
from torrcast.usecases.choice.series_take import series_take
from torrcast.usecases.choice.series_taken_line import series_taken_line
from torrcast.usecases.choice.take import Take
from torrcast.usecases.choice.taken_line import taken_line

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def enter_take(
    plans: list[Plan], asked: str = "", pick: int | None = None, menu: bool = False
) -> Take:
    """Кого включит Enter - и с чем именно сверяется прогрев под меню.

    🔴 Дефолт у прибора ОДИН - :func:`first_alive`, и это та же картина, о которой
    говорят честные строки про смену (:func:`default_note`, :func:`swap_note`,
    :func:`year_note`, :func:`part_one_swap`). Пока Enter брал верх меню, эти двое
    расходились на 23 запросах из 71, и на всех 23 строка молчала - сверялась она с
    одной картиной, а печаталась про другую.

    🔴 Несколько подошедших картин - ещё не повод спрашивать. Вопрос остаётся там, где
    о выборе есть что сказать честной строкой; где сказать нечего (:func:`certain_default`),
    дефолт - первая живая картина - и есть спрошенная. Молчаливым это решение не бывает:
    :func:`taken_line` называет взятую картину, число подошедших и ход к любой другой.

    Стражи части и точного имени не отменяют дефолт на обычном пути: без ``--menu``
    первая живая картина берётся вслух, а строка называет причину и дверь к списку.
    Только явный ``--menu`` отдаёт номер человеку.

    🔴 TC-812. Оба этих стража - и «имя названо целиком» (:func:`named_elsewhere`), и
    тёзки по году - на обычном пути больше НЕ СПРАШИВАЮТ: решение владельца 26-08-2026 -
    «включать самую живую это показатель того что картина популярна а варианты будут уже
    за --menu». Стражи остались стражами: сработавший берёт живейшую не молча
    (:func:`named_taken_line`, :func:`namesake_line`). Дефолт франшизы это не тронуло:
    первая живая часть и её страж (:func:`part_one_swap`) в силе.

    🔴 Вид картины решает ДО живости и только там, где под одним именем нашлись и фильм,
    и сериал (:func:`series_take`): решение владельца 02-09-2026 «без меню между фильмом
    и сериалом выбирать сериал». Внутри выбранного вида решает по-прежнему живость, и
    решение TC-812 «включать самую живую» этим не отменяется.

    🔴 TC-830. «Спрошенная часть в выдаче есть, но не играет» - вопрос за явным ``--menu``:
    её видно номером. А «спрошенной части нет в выдаче вовсе» вопросом быть перестало
    (:func:`absent_first_part`): выбора между «той» и «другой» там не существует. Берётся
    дефолт прибора, и берётся не молча (:func:`absent_part_line`).

    🔴 TC-802. ``menu`` - флаг ``--menu``: список поднимается и там, где о выборе сказать
    нечего. ``pick`` - номер, названный флагом ``--pick N``: вопроса тогда нет вовсе, и
    Enter берёт ровно названное. Номер вне списка сюда не доезжает - его заворачивает
    сам вопрос (:func:`_pick_plan`), а до тех пор греть по нему нечего.

    Терминала под всем этим ступень не спрашивает, и это осознанно: без терминала
    меняется то, СПРОСЯТ ли и откажут ли, а картина, в которую попадёт Enter, - та же.
    Терминал решает речь, речь - забота :func:`_pick_plan`.

    🔴 Каждая ветка подписывается именем правила (``why``), и список этих имён нигде не
    держится руками: зеркало шва (``test_the_warm_and_the_take_cannot_disagree``) вычитывает
    их из ИСХОДНИКА этой функции и требует живого меню под каждое. Новое правило без такого
    меню роняет зеркало, а не проезжает молча.
    """
    if pick is not None and 1 <= pick <= len(plans):
        return Take(pick, why="номер флагом")  # номер назвал человек: ни вопроса, ни подмены
    heading = ""
    if len(plans) == 1:
        if note := lone_other_part(plans, asked):
            if not menu:
                return Take(
                    1,
                    note=lone_other_part_taken_line(plans, asked),
                    why="чужая часть, взята первая живая",
                )
            # Ключ --menu сохраняет страж перед вопросом: список поднимается и из
            # одного пункта, строка печатается НАД ним, чтобы видно было, ЧТО нашлось, -
            # а дефолта она не отменяет: Enter по-прежнему берёт единственный пункт.
            heading = note
        elif not menu:
            return Take(1, why="картина одна")
    default = first_alive(plans)
    if not menu:
        if certain_default(plans, asked):
            return Take(default, note=taken_line(plans, default, asked), why="дефолт без вопроса")
        if absent_first_part(plans, asked):
            return Take(
                default,
                note=absent_part_line(plans, default, asked),
                why="спрошенной части нет",
            )
        if not part_one_swap(plans, asked):
            if taken := named_take(plans, asked):
                return Take(
                    taken,
                    note=named_taken_line(plans, asked, taken),
                    why="имя названо целиком",
                )
            if taken := series_take(plans):
                return Take(
                    taken,
                    note=series_taken_line(plans, taken, asked),
                    why="сериал под одним именем с фильмом",
                )
            if taken := namesake_take(plans):
                return Take(taken, note=namesake_line(plans, taken, asked), why="тёзки по году")
    if note := part_one_swap(plans, asked):
        if not menu:
            return Take(
                default,
                note=part_one_taken_line(plans, default, asked, note),
                why="страж первой части, взята первая живая",
            )
        # За --menu строка называет, что с первой частью, а номер зовёт человек.
        return Take(
            default, takes=False, asks=True, note=note, heading=heading, why="страж первой части"
        )
    if note := named_elsewhere(plans, asked):
        # За явным --menu строка называет обе картины и причину, номер зовёт человек.
        return Take(
            default,
            takes=False,
            asks=True,
            note=note,
            heading=heading,
            why="имя названо, дефолт мимо",
        )
    if not menu:
        return Take(
            default,
            note=default_taken_line(plans, default, asked),
            why="взята первая живая",
        )
    return Take(
        default,
        asks=True,
        note=default_line(plans, default),
        heading=heading,
        why="дефолт с вопросом",
    )
