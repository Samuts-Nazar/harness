"""Word-paced streaming with a cut position."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator


class InterruptHandle:
    """Set by the player's interrupt button; polled between words."""

    def __init__(self) -> None:
        self._ev = threading.Event()

    def request(self) -> None:
        self._ev.set()

    @property
    def requested(self) -> bool:
        return self._ev.is_set()


def iter_words(chunks: Iterable[str]) -> Iterator[str]:
    """Re-assemble whole words from arbitrary chunk boundaries."""
    buf = ""
    for c in chunks:
        buf += c
        parts = buf.split()
        if buf and not buf[-1].isspace():
            buf = parts.pop() if parts else ""
        else:
            buf = ""
        yield from parts
    if buf.strip():
        yield buf.strip()


@dataclass(frozen=True)
class StreamResult:
    spoken: tuple[str, ...]  # words the audience actually received
    tail: tuple[str, ...]  # words generated but cut (never said)
    interrupted: bool

    @property
    def spoken_text(self) -> str:
        return " ".join(self.spoken)

    @property
    def tail_text(self) -> str:
        return " ".join(self.tail)


def run_stream(
    chunks: Iterable[str],
    handle: InterruptHandle | None = None,
    on_word: Callable[[str], None] | None = None,
    pace: float = 0.0,
) -> StreamResult:
    """Deliver words one at a time. If `handle` fires, the current word is the last
    one delivered; the rest of the stream is drained into `tail` without delivery."""
    spoken: list[str] = []
    tail: list[str] = []
    cut = False
    for w in iter_words(chunks):
        if not cut and handle is not None and handle.requested:
            cut = True
        if cut:
            tail.append(w)
            continue
        spoken.append(w)
        if on_word:
            on_word(w)
        if pace:
            time.sleep(pace)
    return StreamResult(tuple(spoken), tuple(tail), cut)
