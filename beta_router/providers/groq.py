import requests

try:
    from .base import BaseProvider
except ImportError:
    from providers.base import BaseProvider

try:
    # beta_routerパッケージとしてimportする場合
    from ..config import (
        GROQ_API_KEY,
        GROQ_BASE_URL,
        GROQ_MODEL,
        SYSTEM_PROMPT,
    )
except ImportError:
    # router.pyを直接CLI実行する場合
    from config import (
        GROQ_API_KEY,
        GROQ_BASE_URL,
        GROQ_MODEL,
        SYSTEM_PROMPT,
    )


class GroqProvider(BaseProvider):
    name = "groq"
    def __init__(
        self,
        api_key: str = GROQ_API_KEY,
        base_url: str = GROQ_BASE_URL,
        model: str = GROQ_MODEL,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEYが設定されていません。"
                "beta_router/.envを確認してください。"
            )

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
            },
            timeout=120,
        )

        response.raise_for_status()
        data = response.json()

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Groqの応答形式が想定外です: {data}"
            ) from exc
