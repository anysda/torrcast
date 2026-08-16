"""Проверяет совместимость старого имени адаптера упаковки."""


def test_old_module_name_is_adapter() -> None:
    import torrcast.adapters.stream_pack as adapter
    import torrcast.stream_pack as facade

    assert facade is adapter
