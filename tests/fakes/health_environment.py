"""Изображает для тестов внешний мир самопроверки и записывает заданные сроки."""

from dataclasses import dataclass, field

from torrcast.ports.health_config import HealthConfig


@dataclass
class FakeHealthEnvironment:
    """Все ответы окружения - поля: тест меняет ровно то, о чём он говорит."""

    tty: bool = True
    utf8: bool | None = True
    charset: str = "utf-8"
    variables: str = "LANG=ru_RU.UTF-8"
    help_text: str | None = "  -readrate_initial_burst <float>"
    version: str | None = "ffmpeg version 7.1"
    unit: str | None = "Environment=DOTNET_SYSTEM_NET_DISABLEIPV6=1"
    payloads: dict[str, object] = field(default_factory=dict)
    titles: list[str] | None = field(default_factory=lambda: ["The Matrix"])
    echo: str | None = "MatriX.130"
    settings: object | None = None
    memory: int = 8 * 1024**3
    free: int = 60 * 1024**3
    port: int = 8009
    address: str = "10.0.0.7"
    refusal: str = ""
    heard: tuple[list[str], str, str] = field(default_factory=lambda: ([], "silence", "тишина"))
    profile: tuple[str, str, bool] = ("Q70D", "по паспорту: Samsung", False)
    base: tuple[str, str] = ("http://10.0.0.7:8080", "")
    days: int | None = None
    shelf: tuple[str, tuple[int, int], tuple[int, int]] = ("/var/lib/torrcast", (1, 2), (3, 4))
    limits: tuple[int, int] = (200, 300)
    journal: tuple[bool, float, int] = (True, 100.0, 2_000_000)
    journal_dir: str = "/var/lib/torrcast/log"
    retain: int = 7
    moment: float = 4000.0
    #: Сроки, с которыми пробы обращались наружу: по ним видно, кто кого не дождётся.
    timeouts: list[float] = field(default_factory=list)
    #: Адреса, которые спрашивали: порядок запросов - часть договора с Prowlarr.
    urls: list[str] = field(default_factory=list)

    def has_terminal(self) -> bool:
        return self.tty

    def terminal_utf8(self) -> bool | None:
        return self.utf8

    def encoding(self) -> str:
        return self.charset

    def locale_env(self) -> str:
        return self.variables

    def ffmpeg_help(self) -> str | None:
        return self.help_text

    def ffmpeg_version(self) -> str | None:
        return self.version

    def prowlarr_unit(self, timeout: float) -> str | None:
        self.timeouts.append(timeout)
        return self.unit

    def get_json(self, url: str, headers: dict[str, str], timeout: float) -> object | None:
        self.timeouts.append(timeout)
        self.urls.append(url)
        return self.payloads.get(url.rsplit("/", 1)[-1])

    def search_titles(
        self, url: str, apikey: str, indexer: int, query: str, timeout: float
    ) -> list[str] | None:
        self.timeouts.append(timeout)
        self.urls.append(f"{url}?{query}#{indexer}")
        return self.titles

    def torrserver_echo(self, url: str, timeout: float) -> str | None:
        self.timeouts.append(timeout)
        return self.echo

    def torrserver_settings(self, url: str, timeout: float) -> object | None:
        self.timeouts.append(timeout)
        return self.settings

    def machine_memory(self) -> int:
        return self.memory

    def disk_free(self, path: str) -> int:
        self.urls.append(path)
        return self.free

    def cast_port(self) -> int:
        return self.port

    def our_address(self, tv: str) -> str:
        return self.address

    def port_error(self, host: str, port: int, timeout: float) -> str:
        self.timeouts.append(timeout)
        return self.refusal

    def heard_receivers(self) -> tuple[list[str], str, str]:
        return self.heard

    def receiver_profile(self, config: HealthConfig) -> tuple[str, str, bool]:
        return self.profile

    def hls_base(self, config: HealthConfig) -> tuple[str, str]:
        return self.base

    def cert_days(self, path: str) -> int | None:
        return self.days

    def shelves(self) -> tuple[str, tuple[int, int], tuple[int, int]]:
        return self.shelf

    def shelf_limits(self) -> tuple[int, int]:
        return self.limits

    def trace_health(self) -> tuple[bool, float, int]:
        return self.journal

    def trace_dir(self) -> str:
        return self.journal_dir

    def retain_days(self) -> int:
        return self.retain

    def now(self) -> float:
        return self.moment
