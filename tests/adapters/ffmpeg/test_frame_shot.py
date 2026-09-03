"""Проверяет запасной путь картинки: один кадр показа настоящим ffmpeg."""

from __future__ import annotations

from pathlib import Path

import pytest

from hass.picture_type import picture_type
from torrcast.adapters.ffmpeg.frame_shot import frame_shot


def test_a_frame_of_a_real_clip_comes_back_as_a_picture(clip: str) -> None:
    """Настоящий ролик, настоящий ffmpeg: на выходе байты, которые карточка нарисует.

    Тип читается той же подписью, какой его назовёт маршрут серва: скажи ffmpeg отдать
    кадр не картинкой, а куском видео - и разошлось бы это молча, пустой карточкой у
    зрителя, а не красным тут.
    """
    shot = frame_shot(clip)

    assert shot is not None and len(shot) > 1000
    assert picture_type(shot) == "image/jpeg"


@pytest.mark.machine
def test_a_source_that_cannot_be_opened_answers_with_nothing(tmp_path: Path) -> None:
    """Показ мог оборваться, а раздача - уехать: тогда кадра нет, и это не отказ серва."""
    assert frame_shot(str(tmp_path / "нет-такого.m3u8")) is None


@pytest.mark.machine
def test_an_empty_result_is_not_taken_for_a_picture(tmp_path: Path) -> None:
    """Файл без видеодорожки ffmpeg открывает, а кадра из него не делает.

    Пустой файл на месте картинки уехал бы в карточку с честным заголовком типа - и
    зритель увидел бы битую картинку вместо запасного кадра.
    """
    silence = tmp_path / "empty.mp4"
    silence.write_bytes(b"")

    assert frame_shot(str(silence)) is None


@pytest.mark.machine
def test_without_ffmpeg_on_the_machine_the_card_still_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 ffmpeg - не условие работы карточки, а условие ЗАПАСНОГО пути.

    Упади тут исключение - и снимок серва отвечал бы отказом на каждый опрос: показ,
    пульт и полоса времени умерли бы из-за отсутствующей картинки.
    """
    monkeypatch.setenv("PATH", str(tmp_path))

    assert frame_shot("http://10.0.1.5:8010/stream/index.m3u8") is None
