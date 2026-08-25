"""Проверяет голову команды упаковки: заход, второй вход и карту дорожек."""

from torrcast.adapters.ffmpeg.pack_inputs import pack_inputs


def test_one_input_names_the_track_inside_the_video() -> None:
    """Без отдельного файла звук берётся из самого видео, и вход ровно один."""
    command = pack_inputs("http://raz/video", 2, None)
    assert command.count("-i") == 1
    assert command[-4:] == ["-map", "0:v:0", "-map", "0:a:2"]
    assert "-ss" not in command


def test_entry_is_named_once_per_input() -> None:
    """Заход называется каждому входу: второй читается с того же места, а не с нуля."""
    command = pack_inputs("http://raz/video", 0, 20.0, voice_url="http://raz/voice")
    assert command.count("-ss") == 2
    assert command[command.index("-i") + 2 : command.index("-i") + 4] == ["-ss", "20.000"]
    assert command[-4:] == ["-map", "0:v:0", "-map", "1:a:0"]


def test_voice_is_read_no_further_than_the_film_ends() -> None:
    """Хвост отдельной дорожки за концом фильма не читается: у второго входа свой ``-t``."""
    command = pack_inputs("http://raz/video", 0, 20.0, voice_url="http://raz/voice", voice_end=61.0)
    assert command[command.index("-t") + 1] == "41.000"
    assert command.index("-t") < command.index("http://raz/voice")


def test_voice_from_the_very_beginning_reads_the_whole_film() -> None:
    """Заход с нуля ``-ss`` не называет, а длину второму входу называет всю."""
    command = pack_inputs("http://raz/video", 0, None, voice_url="http://raz/voice", voice_end=61.0)
    assert "-ss" not in command
    assert command[command.index("-t") + 1] == "61.000"


def test_readrate_and_burst_stand_before_the_inputs() -> None:
    """Темп чтения - свойство прогона, и называется он до первого ``-i``."""
    command = pack_inputs("http://raz/video", 0, None, readrate=8.0, burst=2.5)
    assert command[command.index("-readrate") + 1] == "8"
    assert command[command.index("-readrate_initial_burst") + 1] == "2.5"
    assert command.index("-readrate") < command.index("-i")


def test_no_readrate_means_no_throttle_at_all() -> None:
    """Нулевой темп - это не «читай медленно», а «не придерживай вовсе»."""
    assert "-readrate" not in pack_inputs("http://raz/video", 0, None, readrate=0.0)
