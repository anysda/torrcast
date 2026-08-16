"""Tests for the completed-process value."""

from torrcast.domain.process_result import ProcessResult


def test_defaults_captured_streams_to_empty() -> None:
    assert ProcessResult(0).stdout == ""
