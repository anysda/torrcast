"""Проверяет договор показанного меню: печать разом и переписанная строка."""

from torrcast.ports.menu_paint import MenuPaint


class Screen:
    """Меню, которое всё запоминает: договор держится на трёх действиях и признаке."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.closed = False

    @property
    def live(self) -> bool:
        return True

    def show(self, lines: list[str]) -> None:
        self.lines = list(lines)

    def redraw(self, index: int, line: str) -> None:
        self.lines[index] = line

    def close(self) -> None:
        self.closed = True


def test_a_shown_menu_lets_a_single_line_be_rewritten_in_place() -> None:
    screen = Screen()
    port: MenuPaint = screen

    port.show(["  1. Тачки (2006)", "  2. Тачки 2 (2011)"])
    port.redraw(0, "  1. Тачки (2006) · IMDb 7.1")
    port.close()

    assert port.live
    assert screen.lines == ["  1. Тачки (2006) · IMDb 7.1", "  2. Тачки 2 (2011)"]
    assert screen.closed
