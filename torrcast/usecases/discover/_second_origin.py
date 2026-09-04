"""Справка о картине для второго захода: у кого спрашиваем и что делаем с ответом."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable

from torrcast.domain.facts.origin import Origin


def _second_origin(
    ask: Callable[..., Origin], name: str, kind: bool | None, index: int | None, budget: float
) -> Origin:
    """Паспорт картины перед добором: спрошен вслепую, а номер части снимает с него год.

    Справку спрашиваем вслепую: год выдачи ей не сообщаем, иначе она подстроится под него
    и сверять станет нечего. Тип картины - другое дело, у сериала и фильма разные статьи.
    Сети нет - паспорт пуст, и всё дальше работает ровно так, как работало.
    """
    about = _under_the_hint_and_past_it(ask, name, kind, budget)
    if index is None:
        return about
    # 🔴 Спросили номер части - год справки к делу не относится. Справку зовут по имени
    # франшизы, и отвечает она про её ПЕРВУЮ картину: у «тачек» это 2006 год, а человек
    # просил «тачки 2» - картину 2011-го. Гейт читал это расхождение как подмену и
    # выбрасывал честную выдачу; на живом стенде «тачки 2» так и не находились вовсе.
    # Название латиницей остаётся: номер части у него всё равно отрезан, и оно верное.
    return Origin(title=about.title, name=about.name, guessed=about.guessed)


def _under_the_hint_and_past_it(
    ask: Callable[..., Origin], name: str, kind: bool | None, budget: float
) -> Origin:
    """Оба вопроса к справке разом: под подсказанным типом и мимо него. Верим типу.

    🔴 TC-399. Тип подсказал вожак тощего пула, и под ним справка молчит чаще, чем
    отвечает: подсказка эта слабая - единственная строка тощего пула бывает не картиной
    вовсе. По запросу «lain» приехал самиздатовский журнал «lainzine 1-5», он назвал тип
    «фильм», и справка честно молчала: статьи о фильме «Lain» нет, есть статья о сериале
    «Serial Experiments Lain». Переспрос без типа
    (:func:`~torrcast.usecases.passport_either.PassportEither.of`) спрашивает обе статьи
    разом и верит лишь согласию - подмену он не родит, а молчание разводит.

    Спрашивали их по очереди, и молчание под подсказкой стоило второго полного срока
    справки подряд. Ответ у обоих один и тот же, каким бы порядком их ни спрашивать, так
    что очередь тут не смысл, а только цена: вопросы уходят разом, а верим по-прежнему
    сперва типу и лишь на его молчании - переспросу.

    ⚠️ Цена - один лишний поход в Википедию там, где раньше хватало одного: под
    подсказкой ответили, а переспрос уже уехал. Ждать его в этом случае не за чем, и мы
    не ждём - поток допишет ответ в справку сам
    (:class:`~torrcast.usecases.lookers.Lookers`), и следующему спросившему он достанется
    даром. Значит, лишним получается ЗАПРОС, а не секунда: счастливый путь не платит за
    переспрос ничего.

    Типа не назвали вовсе - переспрашивать нечем: вопрос ровно один, как и был.
    """
    if kind is None:
        return ask(name, series=None, budget=budget)
    deadline = time.monotonic() + budget
    blind: list[Origin] = []

    def past_the_hint() -> None:
        with contextlib.suppress(Exception):
            blind.append(ask(name, series=None, budget=budget))

    aside = threading.Thread(target=past_the_hint, daemon=True, name=f"passport-blind-{name}")
    aside.start()
    about = ask(name, series=kind, budget=budget)
    if about:
        return about
    aside.join(max(0.0, deadline - time.monotonic()))
    return blind[0] if blind else Origin()
