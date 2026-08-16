"""Проверяет совместимость старого имени адаптера перекодирования."""


def test_old_module_name_is_adapter() -> None:
    import torrcast.adapters.recode as adapter
    import torrcast.recode as facade

    assert facade is adapter
