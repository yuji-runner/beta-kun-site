"""NVIDIA NIM Provider。"""

import time

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
except ImportError:
    # beta_routerディレクトリ内から直接実行する場合
    from providers.base import BaseProvider
    from config import (
        NVIDIA_API_KEY,
        NVIDIA_BASE_URL,
        NVIDIA_MODEL,
        SYSTEM_PROMPT,
    )


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

            wait_seconds = 2 ** (attempt - 1)

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
