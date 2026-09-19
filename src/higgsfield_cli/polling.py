"""Polling statusu wg /docs/concepts/polling: 2 s, x1.5, maks. 10 s, jitter, deadline.

Czyste funkcje z wstrzykiwanym zegarem/sleepem — testowalne bez sieci i czekania.
"""

import random
import time
from typing import Callable, Iterator

from . import const
from .client import HfApiError, HfNetworkError


class PollTimeout(Exception):
    def __init__(self, last_status: str | None, waited: float):
        super().__init__(f"Przekroczono limit czasu ({waited:.0f} s), ostatni status: {last_status}")
        self.last_status = last_status
        self.waited = waited


def backoff_delays(initial=const.POLL_INITIAL, factor=const.POLL_FACTOR,
                   maximum=const.POLL_MAX) -> Iterator[float]:
    """Kolejne przerwy bez jittera: 2, 3, 4.5, 6.75, 10, 10, ..."""
    delay = initial
    while True:
        yield delay
        delay = min(delay * factor, maximum)


def poll_until_terminal(
    fetch: Callable[[], dict],
    *,
    timeout: float,
    on_update: Callable[[dict, float], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    jitter: Callable[[], float] = lambda: random.uniform(0, const.POLL_JITTER),
    max_errors: int = const.POLL_MAX_CONSECUTIVE_ERRORS,
) -> dict:
    """Odpytuje fetch() aż do statusu terminalnego; zwraca ostatnią odpowiedź.

    - 5xx / błąd sieci: ponawia z tym samym backoffem (maks. max_errors z rzędu),
    - 401 / 404 / inne 4xx: przerywa od razu (HfApiError idzie wyżej),
    - po `timeout` sekundach: PollTimeout — zadanie dalej trwa po stronie API.
    """
    start = now()
    delays = backoff_delays()
    last_status = None
    errors = 0
    while True:
        try:
            data = fetch()
            errors = 0
            last_status = data.get("status")
            if on_update:
                on_update(data, now() - start)
            if last_status in const.TERMINAL_STATUSES:
                return data
        except (HfApiError, HfNetworkError) as e:
            if isinstance(e, HfApiError) and not e.retryable:
                raise
            errors += 1
            if errors >= max_errors:
                raise
        delay = next(delays) + jitter()
        elapsed = now() - start
        if elapsed + delay > timeout:
            raise PollTimeout(last_status, elapsed)
        sleep(delay)
