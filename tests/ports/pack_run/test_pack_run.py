"""Идущий прогон упаковки: настоящий прогон отвечает на всё, что спрашивает лента."""

from torrcast.adapters.stream_pack.packer import Packer
from torrcast.ports.pack_run.pack_run import PackRun


def test_the_real_run_answers_everything_the_feed_asks() -> None:
    """Договор снят с настоящих вопросов ленты и сверяется тем самым классом.

    Мера не косметическая: пока упаковщик лежал в слое сценариев, лента звала его по
    имени класса, а прогрев - через безымянный слот. Разъехаться договор с прогоном мог
    молча; здесь имя сверяется с тем, что встаёт в слот ленты.
    """
    run: type[PackRun] = Packer

    assert run is Packer
