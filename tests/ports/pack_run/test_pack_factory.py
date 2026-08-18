"""Завод прогона упаковки: настоящий упаковщик под договор ленты подходит."""

from torrcast.adapters.stream_pack.packer import Packer
from torrcast.ports.pack_run import PackFactory


def test_the_real_packer_fits_the_contract_of_the_feed() -> None:
    """Подпись завода снята с настоящих вызовов ленты, а не придумана про запас."""
    factory: PackFactory = Packer

    assert factory is Packer
