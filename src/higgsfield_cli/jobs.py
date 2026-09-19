"""Lokalny rejestr zleceń (~/.higgsfield/jobs.json).

To jest odpowiednik "powiązania request_id z użytkownikiem": narzędzie ma
jednego właściciela (to konto/komputer), więc status/wait/cancel działają
tylko dla request_id zapisanych tutaj. Rejestr służy też do blokowania
duplikatów (odcisk żądania) i wznawiania czekania po przerwaniu.
"""

import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import const

# Zlecenia, których ponowne wysłanie z tymi samymi parametrami to prawie
# na pewno pomyłka (trwa, już gotowe albo POST mógł przejść).
_DUPLICATE_BLOCKING = (const.LOCAL_SUBMITTING, const.LOCAL_SUBMIT_UNKNOWN, *const.ACTIVE_STATUSES, "completed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobStoreError(Exception):
    pass


class JobStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock_path = self.path.with_suffix(".lock")

    @contextmanager
    def _locked(self, timeout: float = 10.0):
        """Prosta blokada plikowa (O_EXCL) — kilka równoległych CLI nie gubi wpisów."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise JobStoreError(f"Rejestr zablokowany: usuń {self._lock_path}, jeśli nic nie działa.")
                time.sleep(0.05)
        try:
            yield
        finally:
            os.close(fd)
            os.unlink(self._lock_path)

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise JobStoreError(f"Uszkodzony rejestr {self.path}: {e}") from e

    def _write(self, jobs: list[dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def all(self) -> list[dict]:
        with self._locked():
            return self._read()

    def get(self, request_id: str) -> dict | None:
        return next((j for j in self.all() if j.get("request_id") == request_id), None)

    def reserve(self, *, kind: str, endpoint: str, arguments: dict, fp: str, force: bool) -> dict:
        """Atomowo: sprawdza duplikat i zapisuje wpis 'submitting' PRZED wysłaniem POST."""
        with self._locked():
            jobs = self._read()
            if not force:
                dup = next((j for j in reversed(jobs)
                            if j["fingerprint"] == fp and j["status"] in _DUPLICATE_BLOCKING), None)
                if dup:
                    return {"duplicate": dup}
            job = {
                "id": uuid.uuid4().hex,
                "request_id": None,
                "kind": kind,
                "endpoint": endpoint,
                "arguments": arguments,
                "fingerprint": fp,
                "status": const.LOCAL_SUBMITTING,
                "created_at": _now(),
                "updated_at": _now(),
                "correlation_id": None,
                "error": None,
                "outputs": [],
                "files": [],
            }
            jobs.append(job)
            self._write(jobs)
            return {"job": job}

    def update(self, job_id: str, **fields) -> dict:
        with self._locked():
            jobs = self._read()
            for job in jobs:
                if job["id"] == job_id:
                    job.update(fields, updated_at=_now())
                    self._write(jobs)
                    return job
        raise JobStoreError(f"Brak zlecenia {job_id} w rejestrze.")
