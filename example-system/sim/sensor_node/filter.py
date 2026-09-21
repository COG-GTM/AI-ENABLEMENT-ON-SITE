"""Moving-average filter (SN-REQ-003). Mirrors src/filter.c."""

from collections import deque


class MovingAverage:
    def __init__(self, window: int = 4) -> None:
        if window < 1:
            raise ValueError("window must be >= 1")
        self.window = window
        self._buf: deque[int] = deque(maxlen=window)

    def reset(self) -> None:
        self._buf.clear()

    def update(self, sample: int) -> int:
        """Push one sample and return the integer average of the samples seen so far."""
        self._buf.append(int(sample))
        total = sum(self._buf)
        n = len(self._buf)
        # C-style division: truncate toward zero, as src/filter.c does.
        q = abs(total) // n
        return q if total >= 0 else -q

    @property
    def count(self) -> int:
        return len(self._buf)
