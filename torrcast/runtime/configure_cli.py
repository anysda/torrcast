"""Внешний мир слоя команд: режим stdin и три собранные команды.

Слой команд (:mod:`torrcast.cli`) не вправе видеть ни адаптеры, ни сборку сеансов, и
имён этих у него нет вовсе. Прежде каждая команда доставала своё строкой с именем
модуля - тем же обходом правила слоёв, каким держался и плоский namespace монолита.
"""

from torrcast.adapters.console.console import terminal
from torrcast.cli.configure import _configure_settings
from torrcast.cli.main import _configure_main
from torrcast.cli.status import _configure_status
from torrcast.cli.stop import _configure_stop
from torrcast.runtime.configure_command import configure_command
from torrcast.runtime.status_command import status_command
from torrcast.runtime.stop_command import stop_command


def configure_cli() -> None:
    """Раздать слою команд режим stdin и три собранные команды."""
    _configure_main(terminal)
    _configure_status(status_command)
    _configure_stop(stop_command)
    _configure_settings(configure_command)
