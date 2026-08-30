"""Что считается здоровым у приёмника: адрес, порт, имена в эфире и профиль.

Зовёт сценарий :mod:`torrcast.usecases.doctor`, сеть и паспорт приносит порт среды.
"""

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.health_verdict import HealthLine, HealthVerdict
from torrcast.domain.uptime_words import uptime_words

#: Хвост объяснения выбора профиля, которым помечен ВЫНУЖДЕННЫЙ осторожный набор:
#: приёмника не спросили или он не ответил (:mod:`torrcast.adapters.chromecast.
#: profile_detector`). Названный руками осторожный профиль этим хвостом не помечен, и
#: подсказывать про него нечего.
#:
#: 🔴 Это КЛЮЧ чужой строки, а не надпись: перевести его тут в отрыве от места, где
#: объяснение собирается, значит молча погасить подсказку - строка сойдётся, а хвост
#: перестанет совпадать, и ни одна ошибка не всплывёт.
FELL_BACK_TO_CAUTIOUS = "беру осторожный"


class ReceiverHealth:
    """Правила строк про ТВ: есть ли кому играть и по каким порогам."""

    @staticmethod
    def unnamed() -> HealthLine:
        """Адреса нет: показывать некуда, и лечится это одной командой."""
        return HealthVerdict.bad(phrase("health.tv_unnamed"))

    @staticmethod
    def mock(tv: str) -> HealthLine:
        """Приёмник-заглушка: наружу ничего не уходит, и это замысел, а не поломка."""
        return HealthVerdict.warn(phrase("health.tv_mock", tv=tv))

    @staticmethod
    def route(tv: str, ours: str) -> HealthLine:
        """Маршрут до ТВ и наша нога, с которой он нас видит."""
        if not ours:
            return HealthVerdict.bad(phrase("health.tv_no_route", tv=tv))
        return HealthVerdict.ok(phrase("health.tv_route", tv=tv, ours=ours))

    @staticmethod
    def port(port: int, error: str) -> HealthLine:
        """Порт приёмника: он открыт даже у спящего Q70D, поэтому закрытый - обесточенный."""
        if error:
            return HealthVerdict.bad(phrase("health.tv_port_shut", port=port, error=error))
        return HealthVerdict.ok(phrase("health.tv_port_open", port=port))

    @staticmethod
    def link(uptime: float, wired: bool | None) -> HealthLine:
        """Аптайм приёмника и то, чем он подключён: первые два вопроса о мёртвом показе.

        Обе цифры читаются одним обычным запросом к странице сведений устройства
        (:func:`torrcast.adapters.chromecast.scan.receiver_link.receiver_link`), поэтому
        строка ничего не стоит и приёмник ею не будится. Оценка тут проходная: аптайм и
        связь показу не мешают ни при каком значении, они его объясняют.

        Сброшенный аптайм читается ПОСМЕРТНО: приёмник, вернувшийся с малым сроком, был
        обесточен или перезагрузился, и это меняет разбор целиком.
        """
        if uptime <= 0 and wired is None:
            return HealthVerdict.warn(phrase("health.tv_no_info"))
        link = phrase(
            {True: "health.link_wired", False: "health.link_wifi", None: "health.link_unnamed"}[
                wired
            ]
        )
        if uptime <= 0:
            return HealthVerdict.ok(phrase("health.tv_link", link=link))
        return HealthVerdict.ok(phrase("health.tv_uptime", uptime=uptime_words(uptime), link=link))

    @staticmethod
    def mdns(titles: list[str], reason: str, note: str) -> HealthLine:
        """Путь поиска приёмников по mDNS: жив ли он, и что именно не так, если имён нет.

        Строка тут из-за старой ложной тревоги: поиск молча возвращал пустой список, и
        «в сети нет мультикаста» было не отличить от «запустили системным python без
        zeroconf». Теперь причину различает сам поиск, а doctor её показывает. Тишина в
        эфире и отказ сети - «внимание», а не «плохо»: адреса найдёт обход подсетей,
        mDNS даёт только имена. Отсутствующий модуль - уже «плохо»: это сломанная
        установка, а не свойство сети.
        """
        if titles:
            return HealthVerdict.ok(
                phrase("health.mdns_heard", count=len(titles), names=", ".join(titles[:3]))
            )
        if reason == "module":
            return HealthVerdict.bad(note)
        return HealthVerdict.warn(note)

    @staticmethod
    def profile(title: str, how: str, cautious: bool) -> HealthLine:
        """Профиль приёмника: по какому набору порогов будет играть показ и откуда он взялся.

        Строка тут ровно потому, что искать это однажды пришлось бы с гипервизора: пороги
        веса куска, терпения и битрейта у двух приёмников разные, и «почему на этом
        телевизоре перекодируется всё подряд» без этой строки не отвечается ничем.

        Осторожный профиль на незнакомом приёмнике - не беда, а замысел: он играет медленнее,
        но играет. Поэтому «внимание» здесь только тогда, когда осторожный набор достался
        приёмнику, которого мы не смогли спросить, - это единственный случай, где строка
        подсказывает человеку, что можно сделать лучше.
        """
        text = phrase("health.tv_profile", title=title, how=how)
        if cautious and how.endswith(FELL_BACK_TO_CAUTIOUS):
            return HealthVerdict.warn(phrase("health.tv_profile_by_hand", text=text))
        return HealthVerdict.ok(text)
