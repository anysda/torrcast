"""Заголовок своего прогона у куска: кому положить рядом, кому приставить впереди."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.world import packer
from torrcast.adapters.stream_pack._own_head import _own_head
from torrcast.domain.head_name import head_name
from torrcast.domain.hls_settings import HEAD_SENT
from torrcast.domain.segment_container import FMP4

if TYPE_CHECKING:
    from pathlib import Path

#: Заголовок копии и заголовок кодировщика: разница у них ровно в визуальной записи.
_COPY_HEAD = b"init-main-77"
_RECODE_HEAD = b"init-baseline-66"
#: Тело куска: что именно в нём лежит, здесь неважно - важно, что оно не менялось.
_FRAMES = b"frames"


def _show(root: Path) -> tuple[Path, Path]:
    """Каталог показа с общим заголовком и каталог перекода рядом с ним."""
    spare = root / "spare"
    spare.mkdir(parents=True, exist_ok=True)
    run = packer(root, container=FMP4, spare=spare)
    (run.out / "init.mp4").write_bytes(_COPY_HEAD)
    return run.out, spare


def test_mpegts_keeps_every_piece_exactly_as_it_was(tmp_path: Path) -> None:
    """Осторожный контейнер не трогаем вовсе: заголовок едет в каждом куске сам."""
    run = packer(tmp_path, spare=tmp_path / "spare")
    piece = run.run / "v1.ts"
    piece.write_bytes(_FRAMES)

    assert _own_head(run, 1, piece, "ужатие") is piece


def test_the_encoder_run_leaves_its_head_beside_the_piece_it_prepared(tmp_path: Path) -> None:
    """Заходов у кодировщика много, пресет у них разный - заголовок ищут у КУСКА."""
    run = packer(tmp_path, container=FMP4, out=tmp_path / "spare")
    (run.run / "init.mp4").write_bytes(_RECODE_HEAD)
    piece = run.run / "v4.m4s"
    piece.write_bytes(_FRAMES)

    assert _own_head(run, 4, piece, "копия") is piece
    assert (run.out / head_name(4)).read_bytes() == _RECODE_HEAD


def test_a_copy_after_a_copy_goes_out_untouched(tmp_path: Path) -> None:
    """Производитель картинки не менялся - кусок обязан уехать байт в байт прежним."""
    out, _ = _show(tmp_path)
    run = packer(tmp_path, container=FMP4, out=out, spare=tmp_path / "spare")
    piece = run.run / "v2.m4s"
    piece.write_bytes(_FRAMES)

    assert _own_head(run, 2, piece, "копия") is piece


def test_a_shrunk_piece_carries_the_head_of_the_encoder_that_made_it(tmp_path: Path) -> None:
    """Ужатое место едет со СВОИМИ параметрами картинки, а не с параметрами копии."""
    out, spare = _show(tmp_path)
    (spare / head_name(2)).write_bytes(_RECODE_HEAD)
    run = packer(tmp_path, container=FMP4, out=out, spare=spare)
    piece = spare / "v2.m4s"
    piece.write_bytes(_FRAMES)

    headed = _own_head(run, 2, piece, "ужатие")

    assert headed != piece
    assert headed.read_bytes() == _RECODE_HEAD + _FRAMES


def test_the_copy_after_a_shrunk_place_takes_the_shared_head_back(tmp_path: Path) -> None:
    """Иначе декодер остался бы настроен кодировщиком, а кадры едут из исходника."""
    out, spare = _show(tmp_path)
    (spare / head_name(2)).write_bytes(_RECODE_HEAD)
    run = packer(tmp_path, container=FMP4, out=out, spare=spare)
    (spare / "v2.m4s").write_bytes(_FRAMES)
    _own_head(run, 2, spare / "v2.m4s", "ужатие")
    piece = run.run / "v3.m4s"
    piece.write_bytes(_FRAMES)

    headed = _own_head(run, 3, piece, "копия")

    assert headed.read_bytes() == _COPY_HEAD + _FRAMES


def test_two_shrunk_places_in_a_row_with_one_head_pay_for_it_once(tmp_path: Path) -> None:
    """Заголовок меняется только там, где он и правда сменился."""
    out, spare = _show(tmp_path)
    (spare / head_name(2)).write_bytes(_RECODE_HEAD)
    (spare / head_name(3)).write_bytes(_RECODE_HEAD)
    run = packer(tmp_path, container=FMP4, out=out, spare=spare)
    (spare / "v2.m4s").write_bytes(_FRAMES)
    _own_head(run, 2, spare / "v2.m4s", "ужатие")
    piece = spare / "v3.m4s"
    piece.write_bytes(_FRAMES)

    assert _own_head(run, 3, piece, "ужатие") is piece


def test_a_second_encoder_pass_with_another_preset_gets_its_own_head(tmp_path: Path) -> None:
    """``ultrafast`` и ``veryfast`` дают разные параметры: общего заголовка перекода нет."""
    out, spare = _show(tmp_path)
    (spare / "init.mp4").write_bytes(_RECODE_HEAD)
    (spare / head_name(5)).write_bytes(b"init-high-100")
    run = packer(tmp_path, container=FMP4, out=out, spare=spare)
    piece = spare / "v5.m4s"
    piece.write_bytes(_FRAMES)

    assert _own_head(run, 5, piece, "перекод").read_bytes() == b"init-high-100" + _FRAMES


def test_a_head_that_arrived_after_the_copy_left_does_not_speak_for_it(tmp_path: Path) -> None:
    """Перекод доезжает и ПОСЛЕ выкладки копии: чей кусок лежит - не чей кусок уехал."""
    out, spare = _show(tmp_path)
    run = packer(tmp_path, container=FMP4, out=out, spare=spare)
    copied = run.run / "v2.m4s"
    copied.write_bytes(_FRAMES)
    _own_head(run, 2, copied, "копия")
    # Кодировщик дописал место 2 уже после того, как оно уехало копией.
    (spare / head_name(2)).write_bytes(_RECODE_HEAD)
    (spare / head_name(3)).write_bytes(_RECODE_HEAD)
    piece = spare / "v3.m4s"
    piece.write_bytes(_FRAMES)

    assert _own_head(run, 3, piece, "ужатие").read_bytes() == _RECODE_HEAD + _FRAMES


def test_the_place_that_went_out_is_written_down_beside_the_encoder_pieces(
    tmp_path: Path,
) -> None:
    """Ответ соседу пишет сама выкладка: другого источника правды про уехавшее нет."""
    out, spare = _show(tmp_path)
    run = packer(tmp_path, container=FMP4, out=out, spare=spare)
    piece = run.run / "v2.m4s"
    piece.write_bytes(_FRAMES)

    _own_head(run, 2, piece, "копия")

    assert (spare / head_name(2, HEAD_SENT)).read_bytes() == _COPY_HEAD


def test_what_the_previous_place_had_is_asked_of_the_disk_not_of_the_run(tmp_path: Path) -> None:
    """Упаковка начинается заново на каждой перемотке, а приёмник помнит заголовок."""
    out, spare = _show(tmp_path)
    (spare / head_name(2)).write_bytes(_RECODE_HEAD)
    first = packer(tmp_path, container=FMP4, out=out, spare=spare)
    (spare / "v2.m4s").write_bytes(_FRAMES)
    _own_head(first, 2, spare / "v2.m4s", "ужатие")

    fresh = packer(tmp_path, container=FMP4, out=out, spare=spare, first=3)
    piece = fresh.run / "v3.m4s"
    piece.write_bytes(_FRAMES)

    assert _own_head(fresh, 3, piece, "копия").read_bytes() == _COPY_HEAD + _FRAMES


def test_the_first_place_of_a_run_takes_its_head_without_asking(tmp_path: Path) -> None:
    """Прыгнуть можно и в место сразу за ужатым: спросить про предыдущее уже некого."""
    out, spare = _show(tmp_path)
    (spare / "init.mp4").write_bytes(_RECODE_HEAD)
    fresh = packer(tmp_path, container=FMP4, out=out, spare=spare, first=9)
    piece = fresh.run / "v9.m4s"
    piece.write_bytes(_FRAMES)

    assert _own_head(fresh, 9, piece, "копия").read_bytes() == _COPY_HEAD + _FRAMES


def test_a_show_without_a_single_encoder_pass_prepends_nothing_at_all(tmp_path: Path) -> None:
    """У показа из одних копий производитель картинки один, и пересобирать нечего."""
    out, spare = _show(tmp_path)
    fresh = packer(tmp_path, container=FMP4, out=out, spare=spare, first=9)
    piece = fresh.run / "v9.m4s"
    piece.write_bytes(_FRAMES)

    assert _own_head(fresh, 9, piece, "копия") is piece
