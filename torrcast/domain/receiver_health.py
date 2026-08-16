"""Что считается здоровым у приёмника: адрес, порт, имена в эфире и профиль.

Зовёт сценарий :mod:`torrcast.usecases.doctor`, сеть и паспорт приносит порт среды.
"""

from torrcast.domain.health_verdict import HealthLine, HealthVerdict


class ReceiverHealth:
    """Правила строк про ТВ: есть ли кому играть и по каким порогам."""

    @staticmethod
    def unnamed() -> HealthLine:
        """Адреса нет: показывать некуда, и лечится это одной командой."""
        return HealthVerdict.bad(
            "адрес ТВ не задан: cast --tv (найдёт приёмники сам) или cast --tv <ip>"
        )

    @staticmethod
    def mock(tv: str) -> HealthLine:
        """Приёмник-заглушка: наружу ничего не уходит, и это замысел, а не поломка."""
        return HealthVerdict.warn(f"приёмник mock ({tv}) - каста наружу нет, это режим проверки")

    @staticmethod
    def route(tv: str, ours: str) -> HealthLine:
        """Маршрут до ТВ и наша нога, с которой он нас видит."""
        if not ours:
            return HealthVerdict.bad(f"до ТВ {tv} нет маршрута - каст не уйдёт")
        return HealthVerdict.ok(f"ТВ {tv} виден с нашей ноги {ours}")

    @staticmethod
    def port(port: int, error: str) -> HealthLine:
        """Порт приёмника: он открыт даже у спящего Q70D, поэтому закрытый - обесточенный."""
        if error:
            return HealthVerdict.bad(f"порт {port} на ТВ не открылся ({error}) - ТВ обесточен?")
        return HealthVerdict.ok(f"порт {port} на ТВ открыт - приёмник примет показ")

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
                f"mDNS: услышал приёмников {len(titles)} ({', '.join(titles[:3])}) - "
                "имена в поиске будут"
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
        text = f"профиль приёмника: {title} - {how}"
        if cautious and how.endswith("беру осторожный"):
            return HealthVerdict.warn(f"{text}; назвать руками - ключ receiver_profile в конфиге")
        return HealthVerdict.ok(text)
