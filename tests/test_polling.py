from itertools import islice

import pytest

from higgsfield_cli.client import HfApiError, HfNetworkError
from higgsfield_cli.polling import PollTimeout, backoff_delays, poll_until_terminal


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def run(responses, timeout=1000, **kw):
    clock = FakeClock()
    it = iter(responses)

    def fetch():
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r

    result = poll_until_terminal(fetch, timeout=timeout, sleep=clock.sleep, now=clock.now,
                                 jitter=lambda: 0.0, **kw)
    return result, clock


def test_backoff_schedule_matches_docs():
    assert list(islice(backoff_delays(), 7)) == [2.0, 3.0, 4.5, 6.75, 10.0, 10.0, 10.0]


def test_stops_on_terminal_and_reports_updates():
    seen = []
    result, clock = run([{"status": "queued"}, {"status": "in_progress"}, {"status": "completed", "x": 1}],
                        on_update=lambda d, t: seen.append(d["status"]))
    assert result["x"] == 1
    assert seen == ["queued", "in_progress", "completed"]
    assert clock.sleeps == [2.0, 3.0]


@pytest.mark.parametrize("terminal", ["failed", "nsfw", "canceled"])
def test_all_terminal_states_stop(terminal):
    result, _ = run([{"status": terminal}])
    assert result["status"] == terminal


def test_retries_5xx_and_network_errors():
    result, clock = run([HfApiError(502, "bad gateway"), HfNetworkError("reset"), {"status": "completed"}])
    assert result["status"] == "completed"
    assert len(clock.sleeps) == 2


@pytest.mark.parametrize("code", [401, 404])
def test_does_not_retry_auth_or_not_found(code):
    with pytest.raises(HfApiError):
        run([HfApiError(code, "nope"), {"status": "completed"}])


def test_gives_up_after_consecutive_errors():
    with pytest.raises(HfNetworkError):
        run([HfNetworkError("x")] * 3, max_errors=3)


def test_timeout_raises_with_last_status():
    with pytest.raises(PollTimeout) as e:
        run([{"status": "in_progress"}] * 100, timeout=20)
    assert e.value.last_status == "in_progress"
