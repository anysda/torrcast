"""Тяжёлый кусок у прогрева адресован диску: лечь обязан, наружу не идёт."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.warm.world import warmer
from torrcast.domain.segment_container import FMP4
from torrcast.usecases.warm.lay_heavy import _lay_heavy
from torrcast.usecases.warm.settings import RUN_DIR
from torrcast.usecases.warm.vault import Vault

if TYPE_CHECKING:
    from pathlib import Path


def test_the_heavy_copy_moves_out_of_the_run_and_onto_the_disk(tmp_path: Path) -> None:
    """Без этого хука выкладка прогрева вставала на первом же таком куске навсегда."""
    warm = warmer(tmp_path)
    run = warm.vault.dir / RUN_DIR
    run.mkdir(parents=True)
    (run / "v1.ts").write_bytes(b"x" * 20_000_000)

    assert _lay_heavy(warm, 1, 20_000_000) is False, "прогрев пообещал выкладке ужатие"
    assert warm.vault.have(1), "тяжёлый кусок не лёг на диск"
    assert not (run / "v1.ts").exists(), "кусок остался копиться в каталоге прогона"


def test_a_missing_piece_is_not_a_crash(tmp_path: Path) -> None:
    """Куска нет - выкладка всё равно идёт дальше: прогрев не имеет права ронять показ."""
    warm = warmer(tmp_path)

    assert _lay_heavy(warm, 1, 0) is False
    assert not warm.vault.have(1)


def test_the_heavy_copy_lands_when_the_receiver_takes_fmp4(tmp_path: Path) -> None:
    """🔴 Приставка берёт FMP4, и заход пакует ``v1.m4s``.

    Имя куска бралось общим :func:`segment_name` без контейнера, то есть осторожным
    умолчанием завода ``v1.ts``. Замена не находила ничего, выкладка сразу за ней стирала
    тяжёлую копию, место оставалось непрогретым навсегда - и точечный перекод, который
    берётся в работу только поверх лежащей копии, не начинался ни разу.
    """
    store = Vault(root=tmp_path / "warm", key="k", budget=1 << 30, floor=0, container=FMP4)
    store.dir.mkdir(parents=True)
    warm = warmer(tmp_path, vault=store)
    run = warm.vault.dir / RUN_DIR
    run.mkdir(parents=True)
    (run / "v1.m4s").write_bytes(b"x" * 30_000_000)

    assert _lay_heavy(warm, 1, 30_000_000) is False, "прогрев пообещал выкладке ужатие"
    assert warm.vault.have(1), "тяжёлый кусок FMP4 не лёг на диск"
    assert not (run / "v1.m4s").exists(), "кусок остался копиться в каталоге прогона"
