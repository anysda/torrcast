"""Процесс захода упаковки: настоящий процесс прогона под сигналы прогрева подходит."""

from torrcast.adapters.stream_pack.packer_state import _Process
from torrcast.ports.warm_environment import WarmProcess


def test_the_real_process_of_a_run_takes_the_signals_of_the_warming() -> None:
    """Прогрев шлёт заходу SIGSTOP и SIGCONT, и шлёт он их процессу самого прогона."""

    def only_signals(process: _Process) -> WarmProcess:
        return process

    assert only_signals is not None
