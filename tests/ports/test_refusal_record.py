"""Порт записи об отказе подъёма: молчаливое умолчание и смена держателя слотом."""

from __future__ import annotations

from torrcast.ports.refusal_record import RefusalRecord, install, refusal_record


def test_the_silent_default_writes_and_reads_nothing() -> None:
    """Без слова композиционного корня писать некуда, и отказ говорится только в консоль.

    Тот же расклад, что у следа до его корня (:class:`torrcast.ports.journal.silent.Silent`):
    зов порта не должен ронять ни умирающий показ, ни самую раннюю сборку процесса.
    """
    port = RefusalRecord()

    port.record("receiver_did_not_answer")
    port.forget()

    assert port.read() is None


def test_the_slot_answers_with_the_installed_keeper() -> None:
    """Держателя назначает корень один раз на процесс, и зовущие видят ровно его."""

    class _Tape(RefusalRecord):
        """Держатель, который записывает каждое слово, что в него положили."""

        def __init__(self) -> None:
            self.words: list[str] = []

        def record(self, reason: str) -> None:
            self.words.append(reason)

    tape = _Tape()
    install(tape)
    try:
        refusal_record().record("receiver_did_not_answer")
        assert tape.words == ["receiver_did_not_answer"], "зов ушёл мимо назначенного держателя"
    finally:
        install(RefusalRecord())
