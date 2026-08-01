#!/usr/bin/env python3
"""Regression tests for task metrics without external API calls."""

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Keep these tests runnable with the stdlib-only Python used by test_runner.
try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = Exception
    requests_stub.ConnectionError = ConnectionError
    requests_stub.Timeout = TimeoutError
    requests_stub.HTTPError = RuntimeError
    sys.modules["requests"] = requests_stub

try:
    import dotenv  # noqa: F401
except ModuleNotFoundError:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: False
    sys.modules["dotenv"] = dotenv_stub

if __package__:
    from . import router, task_metrics
    from .providers import nvidia as nvidia_module
    from .providers.nvidia import NvidiaProvider
    from .task_metrics import TaskMetrics, safe_error_message
else:
    import router
    import task_metrics
    from providers import nvidia as nvidia_module
    from providers.nvidia import NvidiaProvider
    from task_metrics import TaskMetrics, safe_error_message


class FakeResponse:
    def __init__(self, status_code: int, answer: str = "ok") -> None:
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.text = "sensitive provider response"
        self._answer = answer

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._answer}}]}


class TaskMetricsTests(unittest.TestCase):
    def test_beta_router_uses_the_same_metrics_session(self) -> None:
        class FakeProvider:
            def chat(self, prompt: str) -> str:
                return "reviewed"

        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "task_metrics.jsonl"
            beta_router = router.BetaRouter()
            beta_router.providers["groq"] = FakeProvider()

            with (
                patch.object(task_metrics, "METRICS_FILE", log_path),
                patch.object(router, "write_log"),
            ):
                answer = beta_router.ask("短いレビュー", provider="auto")

            self.assertEqual(answer, "reviewed")
            record = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(record["provider"], "groq")
            self.assertEqual(record["logical_provider_calls"], 1)
            self.assertEqual(record["provider_purpose"], "analysis")
            self.assertNotIn("短いレビュー", log_path.read_text(encoding="utf-8"))

    def test_nvidia_retry_is_counted_without_prompt_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "task_metrics.jsonl"
            responses = [FakeResponse(529), FakeResponse(200, "done")]

            with (
                patch.object(task_metrics, "METRICS_FILE", log_path),
                patch.object(
                    nvidia_module.requests,
                    "post",
                    side_effect=responses,
                    create=True,
                ),
                patch.object(nvidia_module.time, "sleep"),
            ):
                metrics = TaskMetrics(
                    repo=Path(directory),
                    command="test",
                    subcommand="nvidia",
                    provider_purpose="retry_test",
                )
                with metrics:
                    metrics.provider_call("nvidia", "retry_test")
                    answer = NvidiaProvider(api_key="nvapi-test-secret").chat(
                        "PROMPT_BODY_MUST_NOT_BE_LOGGED"
                    )

            self.assertEqual(answer, "done")
            record = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(record["logical_provider_calls"], 1)
            self.assertEqual(record["http_attempts"], 2)
            self.assertEqual(record["retry_count"], 1)
            self.assertEqual(record["http_statuses"], [529, 200])
            self.assertEqual(record["provider_wait_sec"], 1.0)
            self.assertEqual(record["prompt_length"], 30)
            self.assertNotIn(
                "PROMPT_BODY_MUST_NOT_BE_LOGGED",
                log_path.read_text(encoding="utf-8"),
            )

    def test_error_message_redacts_secrets_and_response(self) -> None:
        message = safe_error_message(
            "API_KEY=nvapi-secret response=private payload"
        )
        self.assertNotIn("nvapi-secret", message)
        self.assertNotIn("private payload", message)

    def test_metrics_write_failure_is_non_fatal(self) -> None:
        with patch.object(
            task_metrics,
            "METRICS_FILE",
            Path("/proc/task_metrics.jsonl"),
        ):
            metrics = TaskMetrics(repo=None, command="test")
            metrics.finish("success")


if __name__ == "__main__":
    unittest.main()
