"""Что считается здоровым у Prowlarr и его индексеров.

Зовёт сценарий :mod:`torrcast.usecases.doctor`, ответы службы приносит порт среды.
"""

from collections.abc import Iterator

from torrcast.domain.health_verdict import HealthLine, HealthVerdict

#: Опорные источники каталога: те, без которых пул не беднеет, а пустеет (замер по
#: журналу запросов: без метапоиска пул пуст у 72 запросов из 93, без обоих - у 97 из 99).
#: Остальные индексеры узкие и этой дыры не закрывают. Имя - как его зовёт Prowlarr, за
#: ним то, что источник даёт каталогу, и то, чего в выдаче не хватит без него. Поиск без
#: опорного продолжает работать, поэтому это «внимание», а не «плохо», - но молчать
#: нельзя: урезанная выдача выглядит как пустой поиск без причины.
#: 🔴 TC-697. Опорных ДВА, и установка отправляет человека смотреть их состояние именно
#: сюда (``install.sh``: тот же ``CORE_INDEXERS``), поэтому строка нужна на каждого.
CORE_INDEXERS = {
    "Knaben": ("западные релизы и аниме", "западных релизов и аниме"),
    "RuTor": ("русские раздачи и озвучки", "русских раздач и озвучек"),
}
#: Ручка, которой Prowlarr запрещено ходить по IPv6 (TC-311). Её же ставит установка.
IPV4_ONLY = "DOTNET_SYSTEM_NET_DISABLEIPV6=1"


class IndexerHealth:
    """Правила строк про поиск: дорога к трекерам, паузы, живой ответ и метапоиск."""

    @staticmethod
    def route(unit: str | None) -> HealthLine:
        """Какой дорогой Prowlarr идёт к трекерам: по IPv4 или как ляжет (TC-311).

        🔴 Проверка дешёвая, а стережёт дорогую ошибку. По IPv6 ответы трекеров обрываются
        РАНЬШЕ, чем по IPv4 (замер тем же мгновением и тем же запросом: у одного имени
        13.4-13.9 КБ против 17.5-18.9 КБ, у другого 15.0-16.4 КБ против 20.5 КБ, шесть попыток
        из шести), а по умолчанию Prowlarr берёт именно IPv6 - это видно в снимке соединений
        во время живого поиска. Итог такой ошибки не «медленнее», а «индексер молчит», и
        выглядит это как пустой поиск.

        Ставит эту ручку установка; строка тут - про машину, которую с тех пор поправили
        мимо неё. ``unit`` - ``None``, когда службой мы не управляем. Порядок семейств в
        системе (`/etc/gai.conf`) смотреть бесполезно: замерено, что Prowlarr его не слушает.
        """
        if unit is None:
            return HealthVerdict.warn(
                "службой Prowlarr не управляем - какой дорогой он идёт к трекерам, не видно"
            )
        if IPV4_ONLY in unit:
            return HealthVerdict.ok(
                "Prowlarr ходит к трекерам по IPv4 - по IPv6 их ответы обрываются раньше"
            )
        return HealthVerdict.warn(
            "Prowlarr может пойти к трекеру по IPv6, а по нему ответы обрываются раньше - "
            "индексер замолчит, и выглядеть это будет как пустой поиск; лечится строкой "
            f"«{IPV4_ONLY}» в его юните (её ставит установка)"
        )

    @staticmethod
    def no_apikey() -> HealthLine:
        """Пустой ключ: искать нечем ещё до всякой сети."""
        return HealthVerdict.bad("Prowlarr: apikey пуст - искать нечем, перезапусти ./install.sh")

    @staticmethod
    def silent(url: str) -> HealthLine:
        """Служба не ответила: поиска не будет вовсе."""
        return HealthVerdict.bad(f"Prowlarr не отвечает ({url}) - поиска не будет")

    @staticmethod
    def count(url: str, count: int) -> HealthLine:
        """Сколько индексеров завела установка; ноль - это поломка, а не настройка."""
        if not count:
            return HealthVerdict.bad(f"Prowlarr отвечает, но индексеров ноль ({url})")
        return HealthVerdict.ok(f"Prowlarr отвечает, индексеров {count} ({url})")

    @staticmethod
    def paused(indexers: object, statuses: object) -> Iterator[HealthLine]:
        """Паузы Prowlarr по именам: голый номер индексера человеку ничего не говорит."""
        if not isinstance(indexers, list) or not isinstance(statuses, list):
            return
        names = {
            entry.get("id"): entry.get("name")
            for entry in indexers
            if isinstance(entry, dict) and isinstance(entry.get("name"), str)
        }
        for status in statuses:
            if not isinstance(status, dict) or not status.get("disabledTill"):
                continue
            name = names.get(status.get("indexerId"), str(status.get("indexerId") or "?"))
            till = str(status["disabledTill"]).replace("T", " ").removesuffix("Z")
            yield HealthVerdict.bad(f"индексер {name} отключён Prowlarr до {till}")

    @staticmethod
    def probed(payload: object) -> list[tuple[int, str]]:
        """Кого вообще имеет смысл щупать живым поиском: включённых и с внятным номером."""
        if not isinstance(payload, list):
            return []
        return [
            (int(entry["id"]), str(entry["name"]))
            for entry in payload
            if isinstance(entry, dict)
            and entry.get("enable", True)
            and str(entry.get("id", "")).isdigit()
            and isinstance(entry.get("name"), str)
        ]

    @staticmethod
    def answered(name: str, answer: str) -> HealthLine:
        """Итог живого поиска по одному индексеру: молчание и мимо - обе поломки."""
        if answer == "answered":
            return HealthVerdict.ok(f"индексер {name} ответил на живой поиск")
        if answer == "irrelevant":
            return HealthVerdict.bad(
                f"индексер {name} ответил мимо контрольного запроса - выдача ненадёжна"
            )
        return HealthVerdict.bad(f"индексер {name} не ответил на живой поиск - выдача неполная")

    @staticmethod
    def query(name: str) -> str:
        """Контрольный запрос: у аниме-индексера своё имя, которое он обязан знать."""
        return "Kaiba" if "anilibria" in name.casefold() else "matrix"

    @staticmethod
    def answer(query: str, titles: list[str] | None) -> str:
        """Отличает полезный ответ от тишины и от нечёткого совпадения мимо запроса."""
        if not titles:
            return "silent"
        if query == "Kaiba" and not any(query.casefold() in title.casefold() for title in titles):
            return "irrelevant"
        return "answered"

    @staticmethod
    def enabled_names(payload: object) -> list[str]:
        """Имена включённых индексеров из ответа Prowlarr; выключенный не ищет."""
        if not isinstance(payload, list):
            return []
        names: list[str] = []
        for entry in payload:
            if not isinstance(entry, dict) or not entry.get("enable", True):
                continue
            name = entry.get("name")
            if isinstance(name, str):
                names.append(name)
        return names

    @staticmethod
    def core(payload: object) -> Iterator[HealthLine]:
        """Опорные источники, строка на каждого: есть и включён - или выдача неполная."""
        enabled = [name.lower() for name in IndexerHealth.enabled_names(payload)]
        for indexer, (gives, misses) in CORE_INDEXERS.items():
            if any(indexer.lower() in name for name in enabled):
                yield HealthVerdict.ok(f"{indexer} на месте - {gives} в каталоге есть")
            else:
                yield HealthVerdict.warn(
                    f"{indexer} не заведён или выключен - искать можно, но {misses} в выдаче "
                    "будет заметно меньше; вернуть - ./install.sh"
                )
