from torrcast.state import Entry as Entry

__all__ = ["Entry", "_say_showing"]

def _say_showing(live: tuple[str, Entry] | None) -> None: ...
