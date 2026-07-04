"""RxBuffer token parsing — pure, zero I/O.

The invariant under test: parse by searching for tokens, never fixed-size
reads, and bytes past a matched marker belong to the NEXT read.
"""

import pytest

from selfaware.hardware.raw_repl import EOT, OK_MARKER, RxBuffer


def test_take_until_returns_none_when_marker_absent() -> None:
    buf = RxBuffer()
    buf.feed(b"partial data with no marker")
    assert buf.take_until(b"\x04") is None
    # nothing consumed by a failed search
    assert len(buf) == len(b"partial data with no marker")


def test_partial_feeds_accumulate() -> None:
    buf = RxBuffer()
    buf.feed(b"he")
    assert buf.take_until(OK_MARKER) is None
    buf.feed(b"llo")
    assert buf.take_until(OK_MARKER) is None
    buf.feed(OK_MARKER)
    assert buf.take_until(OK_MARKER) == b"hello"


def test_marker_split_across_feeds() -> None:
    buf = RxBuffer()
    buf.feed(b"stdout hereO")  # first half of b"OK"
    assert buf.take_until(OK_MARKER) is None
    buf.feed(b"K")  # second half lands
    assert buf.take_until(OK_MARKER) == b"stdout here"


def test_bytes_past_marker_are_preserved_for_next_read() -> None:
    buf = RxBuffer()
    buf.feed(b"first" + EOT + b"second" + EOT + b">")
    assert buf.take_until(EOT) == b"first"
    assert buf.take_until(EOT) == b"second"
    # the trailing raw-REPL prompt is still there for its own consumption step
    assert buf.take_until(b">") == b""
    assert len(buf) == 0


def test_exec_reply_frame_walkthrough() -> None:
    """The real reply shape: OK + stdout + EOT + stderr + EOT + '>'."""
    buf = RxBuffer()
    traceback = b'Traceback (most recent call last):\r\n  File "<stdin>", line 1\r\nValueError: boom\r\n'
    buf.feed(OK_MARKER + b"42\r\n" + EOT + traceback + EOT + b">")
    assert buf.take_until(OK_MARKER) == b""
    assert buf.take_until(EOT) == b"42\r\n"
    assert buf.take_until(EOT) == traceback
    assert buf.take_until(b">") == b""


def test_clear_drops_everything() -> None:
    buf = RxBuffer()
    buf.feed(b"stale bytes from a wedged exchange")
    buf.clear()
    assert len(buf) == 0
    assert buf.take_until(b"s") is None


def test_empty_marker_rejected() -> None:
    buf = RxBuffer()
    with pytest.raises(ValueError):
        buf.take_until(b"")
