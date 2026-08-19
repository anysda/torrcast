"""План перекода: договор его возит и читать не разрешает."""

from torrcast.adapters.recode.encode import Encode
from torrcast.ports.warm_environment.encode_plan import EncodePlan


def test_the_real_encode_plan_fits_the_carrier() -> None:
    """Имя пустое нарочно: аргументы видео достаёт сборка команды, а не прогрев."""
    carried: EncodePlan = Encode(preset="ultrafast", mbit=1.0)

    assert isinstance(carried, Encode)
