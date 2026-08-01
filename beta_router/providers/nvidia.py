"""NVIDIA NIM Provider。"""

import time
from pathlib import Path

import requests

try:
    # beta_routerパッケージとして読み込む場合
    from .base import BaseProvider
    from ..config import (
        NVIDIA_API_KEY,
        NVIDIA_BASE_URL,
        NVIDIA_MODEL,
        SYSTEM_PROMPT,
    )
    from ..task_metrics import TaskMetrics, current_metrics
except ImportError:
    # beta_routerディレクトリ内から直接実行する場合
    from providers.base import BaseProvider
    from config import (
        NVIDIA_API_KEY,
        NVIDIA_BASE_URL,
        NVIDIA_MODEL,
        SYSTEM_PROMPT,
    )
    from task_metrics import TaskMetrics, current_metrics


class NvidiaProvider(BaseProvider):
    name = "nvidia"

    def __init__(
        self,
        api_key: str = NVIDIA_API_KEY,
        base_url: str = NVIDIA_BASE_URL,
        model: str = NVIDIA_MODEL,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, prompt: str) -> str:
        metrics = current_metrics()
        owns_metrics = metrics is None
        if metrics is None:
            metrics = TaskMetrics(
                repo=Path(__file__).resolve().parents[2],
                command="provider",
                subcommand="chat",
                task_description="Direct provider call",
                provider=self.name,
                provider_purpose="direct",
            )
            metrics.__enter__()

        if owns_metrics:
            metrics.provider_call(self.name, "direct")
        metrics.prompt_length = len(prompt)

        try:
            answer = self._chat(prompt, metrics)
        except Exception as exc:
            if owns_metrics:
                metrics.close("error", error=exc)
            raise
        if owns_metrics:
            metrics.close("success")
        return answer

    def _chat(self, prompt: str, metrics: TaskMetrics) -> str:
        if not self.api_key:
            raise RuntimeError(
                "NVIDIA_API_KEYが設定されていません。"
                "beta_router/.envを確認してください。"
            )

        retry_statuses = {
            429,
            500,
            502,
            503,
            504,
            529,
        }
        max_attempts = 4

        response = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": SYSTEM_PROMPT,
                            },
                            {
                                "role": "user",
                                "content": prompt,
                            },
                        ],
                        "temperature": 0.2,
                        "max_tokens": 1600,
                        "stream": False,
                    },
                    timeout=(5, 120),
                )
            except requests.RequestException:
                metrics.http_attempt(status="request_error")
                raise

            retry = (
                not response.ok
                and response.status_code in retry_statuses
                and attempt < max_attempts
            )
            wait_seconds = 2 ** (attempt - 1) if retry else 0
            metrics.http_attempt(
                status=response.status_code,
                retry=retry,
                wait_sec=wait_seconds,
            )

            if response.ok:
                break

            response_text = (response.text or "").strip()

            if (
                response.status_code not in retry_statuses
                or attempt == max_attempts
            ):
                raise RuntimeError(
                    "NVIDIA NIM APIエラー: "
                    f"HTTP {response.status_code} "
                    f"model={self.model} "
                    f"attempt={attempt}/{max_attempts} "
                    f"response={response_text[:1000] or '(空のレスポンス)'}"
                )

            print(
                "⚠ NVIDIA NIM一時エラー: "
                f"HTTP {response.status_code} "
                f"再試行 {attempt}/{max_attempts} "
                f"{wait_seconds}秒待機",
                flush=True,
            )

            time.sleep(wait_seconds)

        if response is None:
            raise RuntimeError(
                "NVIDIA NIM APIから応答を取得できませんでした。"
            )

        data = response.json()

        try:
            answer = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"NVIDIA NIMの応答形式が想定外です: {data}"
            ) from exc

        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError(
                "NVIDIA NIMから空の回答が返りました。"
            )

        return answer.strip()
