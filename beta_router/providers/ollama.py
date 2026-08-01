import requests

try:
    from .base import BaseProvider
except ImportError:
    from providers.base import BaseProvider

try:
    # beta_routerパッケージとしてimportする場合
    from ..config import (
        OLLAMA_HOST,
        OLLAMA_MODEL,
        SYSTEM_PROMPT,
    )
except ImportError:
    # router.pyを直接CLI実行する場合
    from config import (
        OLLAMA_HOST,
        OLLAMA_MODEL,
        SYSTEM_PROMPT,
    )


class OllamaProvider(BaseProvider):
    name = "ollama"
    def __init__(
        self,
        host: str = OLLAMA_HOST,
        model: str = OLLAMA_MODEL,
    ):
        self.host = host.rstrip("/")
        self.model = model

    def chat(self, prompt: str) -> str:
        response = requests.post(
            f"{self.host}/api/chat",
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
                "stream": False,
                "options": {
                    "temperature": 0.2,
                },
            },
            timeout=120,
        )

        response.raise_for_status()
        data = response.json()

        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                f"Ollamaの応答形式が想定外です: {data}"
            ) from exc
