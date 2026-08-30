"""Три оценки самопроверки и их вид в строке ``cast doctor``.

Зовут все правила здоровья домена и сценарий :mod:`torrcast.usecases.doctor`.
"""

from torrcast.domain.catalogs.phrase import phrase

#: Строка вывода и признак «всё ли хорошо»: по нему считается код возврата команды.
HealthLine = tuple[str, bool]


class HealthVerdict:
    """Чем оценка отличается от оценки: словом слева и весом в итоговом коде.

    Отступы разной ширины подобраны так, чтобы тексты строк шли столбиком: «ок» короче
    «внимания» ровно на те пробелы, которые за ним стоят. «Внимание» проходное - это
    оценка тому, что показу не мешает, но объясняет урезанный результат заранее.

    Столбик держит каждый язык у себя (:mod:`torrcast.domain.catalogs.health`): по-русски
    и по-английски слова разной длины, и добивать пробелы в коде значило бы считать
    ширину одного языка законом для всех.
    """

    @staticmethod
    def ok(text: str) -> HealthLine:
        """Здоров: строка ни на что не влияет, кроме спокойствия человека."""
        return phrase("health.ok", text=text), True

    @staticmethod
    def warn(text: str) -> HealthLine:
        """Работать будет, но хуже: вердикт остаётся проходным."""
        return phrase("health.warn", text=text), True

    @staticmethod
    def bad(text: str) -> HealthLine:
        """Сломано: одна такая строка уводит ``cast doctor`` в код 2."""
        return phrase("health.bad", text=text), False
