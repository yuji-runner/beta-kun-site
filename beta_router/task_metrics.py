"""Best-effort task metrics for the Codex support workflow."""

from __future__ import annotations

import json
import re
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
METRICS_FILE = BASE_DIR / "logs" / "task_metrics.jsonl"
MAX_ERROR_CHARS = 300

_current_session: ContextVar["TaskMetrics | None"] = ContextVar(
    "task_metrics_session",
    default=None,
)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def safe_error_message(error: BaseException | str | None) -> str | None:
    """Return a short error without common credential-like values."""
    if error is None:
        return None

    message = str(error).replace("\n", " ").replace("\r", " ")
    for pattern in (
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+",
        r"(?i)((?:api[_-]?key|token|secret)\s*[:=]\s*)[^\s,;]+",
        r"(?i)(response\s*=).*",
    ):
        message = re.sub(pattern, r"\1[REDACTED]", message)
    message = re.sub(
        r"\b(?:sk|nvapi)-[A-Za-z0-9_.-]+",
        "[REDACTED]",
        message,
    )

    return message[:MAX_ERROR_CHARS]


def _write_record(record: dict[str, Any]) -> None:
    """Append a record, never allowing telemetry failure to break work."""
    try:
        METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with METRICS_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError):
        return


def read_task_records(task_id: str) -> list[dict[str, Any]]:
    """Best-effort read of records for one task without changing JSONL."""
    try:
        records = []
        for line in METRICS_FILE.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except (TypeError, ValueError):
                continue
            if record.get("task_id") == task_id:
                records.append(record)
        return records
    except OSError:
        return []


def summarize_task(task_id: str) -> dict[str, Any]:
    records = read_task_records(task_id)
    subcommands = [item.get("subcommand") for item in records]
    starts = [item.get("timestamp_start") for item in records if item.get("timestamp_start")]
    first = min(starts) if starts else None
    try:
        total_elapsed = (datetime.now().astimezone() - datetime.fromisoformat(first)).total_seconds() if first else 0.0
    except (TypeError, ValueError):
        total_elapsed = 0.0
    return {
        "task_total_elapsed_sec": round(total_elapsed, 3),
        "command_count": len(records) + 1,
        "accumulated_command_time_sec": round(sum(float(item.get("command_elapsed_sec") or 0) for item in records), 3),
        "provider_wait_sec": round(sum(float(item.get("provider_wait_sec") or 0) for item in records), 3),
        "logical_provider_calls": sum(int(item.get("logical_provider_calls") or 0) for item in records),
        "http_attempts": sum(int(item.get("http_attempts") or 0) for item in records),
        "retry_count": sum(int(item.get("retry_count") or 0) for item in records),
        "fallback_count": sum(int(item.get("fallback_count") or 0) for item in records),
        "search_count": subcommands.count("search"),
        "diff_count": subcommands.count("diff"),
        "test_count": subcommands.count("test"),
        "duplicate_finish": "finish" in subcommands,
        "timestamp_first": first,
    }


class TaskMetrics:
    """Collect one command's timing and provider counters."""

    def __init__(
        self,
        *,
        repo: Path | str | None,
        command: str,
        subcommand: str | None = None,
        task_description: str | None = None,
        task_id: str | None = None,
        provider: str | None = None,
        provider_purpose: str | None = None,
        test_target: str | None = None,
        additional_instruction_count: int = 0,
        rework_count: int = 0,
    ) -> None:
        self.task_id = task_id or uuid.uuid4().hex
        self.repo = str(Path(repo).expanduser().resolve()) if repo else None
        self.command = command
        self.subcommand = subcommand
        self.task_description = task_description
        self.provider = provider
        self.provider_purpose = provider_purpose
        self.test_target = test_target
        self.additional_instruction_count = additional_instruction_count
        self.rework_count = rework_count
        self.timestamp_start = now_iso()
        self._started = time.perf_counter()
        self.logical_provider_calls = 0
        self.http_attempts = 0
        self.retry_count = 0
        self.fallback_count = 0
        self.wait_sec = 0.0
        self.http_statuses: list[int | str] = []
        self.prompt_length: int | None = None
        self.prompt_generated: bool | None = None
        self.test_status: str | None = None
        self._token = None
        self._finished = False
        self.extra_fields: dict[str, Any] = {}

    def __enter__(self) -> "TaskMetrics":
        self._token = _current_session.set(self)
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.finish("error" if exc is not None else "success", error=exc)
        if self._token is not None:
            _current_session.reset(self._token)
        return False

    def provider_call(self, provider: str, purpose: str | None = None) -> None:
        self.logical_provider_calls += 1
        self.provider = provider
        if purpose:
            self.provider_purpose = purpose

    def http_attempt(
        self,
        *,
        status: int | str,
        retry: bool = False,
        wait_sec: float = 0.0,
    ) -> None:
        self.http_attempts += 1
        self.http_statuses.append(status)
        if retry:
            self.retry_count += 1
        self.wait_sec += wait_sec

    def finish(
        self,
        status: str,
        *,
        error: BaseException | str | None = None,
    ) -> None:
        if self._finished:
            return
        self._finished = True
        timestamp_end = now_iso()
        record = {
            "record_type": "task",
            "task_id": self.task_id,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": timestamp_end,
            "elapsed_sec": round(time.perf_counter() - self._started, 3),
            "repo": self.repo,
            "task_description": self.task_description,
            "command": self.command,
            "subcommand": self.subcommand,
            "command_elapsed_sec": round(time.perf_counter() - self._started, 3),
            "status": status,
            "provider": self.provider,
            "provider_purpose": self.provider_purpose,
            "logical_provider_calls": self.logical_provider_calls,
            "http_attempts": self.http_attempts,
            "retry_count": self.retry_count,
            "fallback_count": self.fallback_count,
            "provider_wait_sec": round(self.wait_sec, 3),
            "http_statuses": self.http_statuses,
            "prompt_length": self.prompt_length,
            "prompt_generated": self.prompt_generated,
            "test_target": self.test_target,
            "test_status": self.test_status,
            "additional_instruction_count": self.additional_instruction_count,
            "rework_count": self.rework_count,
            "error_type": type(error).__name__ if isinstance(error, BaseException) else None,
            "error_message": safe_error_message(error),
        }
        record.update(self.extra_fields)
        _write_record(record)

    def close(
        self,
        status: str,
        *,
        error: BaseException | str | None = None,
    ) -> None:
        self.finish(status, error=error)
        if self._token is not None:
            _current_session.reset(self._token)
            self._token = None


def current_metrics() -> TaskMetrics | None:
    return _current_session.get()
