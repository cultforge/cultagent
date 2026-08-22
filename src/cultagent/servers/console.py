"""In-memory console / log ring buffer for a managed process."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class ConsoleLine:
    ts: float
    text: str


class ConsoleBuffer:
    def __init__(self, capacity: int = 5000) -> None:
        self._lines: deque[ConsoleLine] = deque(maxlen=capacity)
        self._cond = asyncio.Condition()
        self._seq = 0

    async def append(self, text: str) -> None:
        line = ConsoleLine(ts=time.time(), text=text.rstrip("\r\n"))
        async with self._cond:
            self._lines.append(line)
            self._seq += 1
            self._cond.notify_all()

    def read(self, *, limit: int = 200, after_seq: int = 0) -> dict:
        items = list(self._lines)
        # after_seq is absolute from start of buffer lifetime; approximate via slice.
        if after_seq > 0:
            start = max(0, len(items) - (self._seq - after_seq))
            items = items[start:]
        if limit > 0:
            items = items[-limit:]
        return {
            "seq": self._seq,
            "next_seq": self._seq,
            "lines": [
                {"ts": i.ts, "text": i.text, "seq": self._seq - len(items) + idx + 1}
                for idx, i in enumerate(items)
            ],
        }

    async def wait_for_lines(self, *, after_seq: int, timeout: float = 30.0) -> dict:
        async with self._cond:
            try:
                await asyncio.wait_for(
                    self._cond.wait_for(lambda: self._seq > after_seq),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                pass
        return self.read(after_seq=after_seq)
