"""Проверяет совместимость старого имени адаптера исследования потока."""


def test_old_module_name_is_adapter() -> None:
    import torrcast.adapters.stream_probe as adapter
    import torrcast.stream_probe as facade

    assert facade is adapter
