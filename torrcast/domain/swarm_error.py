"""Ошибка SwarmError; используется публичным API."""

from torrcast.domain.infra_error import InfraError


class SwarmError(InfraError):
    """Раздача не ответила: о её содержимом ничего не известно.

    ``waited`` - сколько секунд рой молчал, числом и рядом с отказом. Носитель заведён
    затем, что приговор терпения (:func:`torrcast.usecases.select._verdict._waiting_note`)
    называет это число человеку, а взять его больше неоткуда: сама жалоба пишется языком
    зрителя и правится, и разбор её регуляркой держался ровно до перевода кластера. Тот
    же договор, что и у :func:`~torrcast.usecases.select._verdict._silenced`: опознаётся
    ТИПОМ отказа и его полями, а не текстом.

    ``None`` - это «сколько ждали, отсюда не видно» (скажем, молчание роя, замеченное
    паспортом), и приговор тогда называет терпение без числа.
    """

    def __init__(self, message: str, waited: float | None = None) -> None:
        super().__init__(message)
        self.waited = waited
