"""Завод захода упаковки: настоящий упаковщик под договор прогрева подходит."""

from torrcast.ports.warm_environment import WarmPacker
from torrcast.usecases.feed_pack.packer import Packer


def test_the_real_packer_fits_the_warming_contract() -> None:
    """Договор снят с настоящего вызова, и проверяется он настоящим упаковщиком.

    Мера не косметическая: в порту стоял ``object``, и разъехаться договор с упаковщиком
    мог молча - прогрев зовёт его через слот среды, а слот до этой карточки был
    безымянным. Здесь имя сверяется с тем самым классом, который встаёт в слот.
    """
    packer: WarmPacker = Packer

    assert packer is Packer
