"""Пробы ``cast doctor`` про путь показа: раздача, ТВ, профиль, полки и след.

Зовёт сценарий :mod:`torrcast.usecases.doctor`, факты берёт у порта среды.
"""

from collections.abc import Iterator

from torrcast.domain.cache_health import CacheHealth
from torrcast.domain.health_verdict import HealthLine
from torrcast.domain.receiver_health import ReceiverHealth
from torrcast.domain.serve_health import ServeHealth
from torrcast.ports.health_config import HealthConfig
from torrcast.ports.health_environment import HealthEnvironment


class ShowCheckup:
    """Всё, что должно быть живо между торрентом и экраном."""

    def __init__(self, environment: HealthEnvironment, timeout: float) -> None:
        self._environment = environment
        self._timeout = timeout

    def torrserver(self, config: HealthConfig) -> HealthLine:
        """Служба раздачи: без неё показывать нечего."""
        echo = self._environment.torrserver_echo(config.torrserver_url, self._timeout)
        return CacheHealth.server(config.torrserver_url, echo)

    def tv(self, config: HealthConfig) -> Iterator[HealthLine]:
        """Адрес ТВ, маршрут до него и порт приёмника - он открыт даже у спящего Q70D."""
        tv = config.tv or ""
        if not tv:
            yield ReceiverHealth.unnamed()
            return
        if config.receiver == "mock":
            yield ReceiverHealth.mock(tv)
            return
        ours = self._environment.our_address(tv)
        yield ReceiverHealth.route(tv, ours)
        if not ours:
            return
        port = self._environment.cast_port()
        yield ReceiverHealth.port(port, self._environment.port_error(tv, port, self._timeout))

    def profile(self, config: HealthConfig) -> HealthLine:
        """Профиль приёмника: по каким порогам будет играть показ и откуда они взялись."""
        return ReceiverHealth.profile(*self._environment.receiver_profile(config))

    def hls(self, config: HealthConfig) -> HealthLine:
        """Адрес раздачи и, если кто-то включил https, свежесть серта."""
        base, error = self._environment.hls_base(config)
        https = config.transport == "https"
        days = self._environment.cert_days(config.hls_cert) if https and not error else None
        return ServeHealth.hls(base, error, https, config.hls_cert, days)

    def shelves(self) -> HealthLine:
        """Кэши карт опорных кадров и паспортов: сколько записей и сколько это весит."""
        shelf, keys, probe = self._environment.shelves()
        keys_kept, probe_kept = self._environment.shelf_limits()
        return ServeHealth.shelves(shelf, keys, keys_kept, probe, probe_kept)

    def trace(self) -> HealthLine:
        """Недельный след: пишется ли он вообще, свежий ли и сколько занимает."""
        found, newest, total = self._environment.trace_health()
        return ServeHealth.trace(
            found,
            self._environment.now() - newest,
            total,
            self._environment.trace_dir(),
            self._environment.retain_days(),
        )
