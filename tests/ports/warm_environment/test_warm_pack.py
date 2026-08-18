"""Идущий заход упаковки: настоящий заход отвечает на все вопросы прогрева."""

from torrcast.ports.warm_environment import WarmPack
from torrcast.usecases.feed_pack.packer import Packer


def test_the_real_run_of_the_packer_answers_everything_the_warming_asks() -> None:
    """Прогрев спрашивает у захода край, выкладку, живость и гашение - и только их."""
    run: type[WarmPack] = Packer

    assert run is Packer
