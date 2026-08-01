"""βRouter Provider共通インターフェース。"""

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """すべてのAI Providerが実装する共通インターフェース。"""

    name: str

    @abstractmethod
    def chat(self, prompt: str) -> str:
        """プロンプトを送信し、回答文字列を返す。"""
        raise NotImplementedError
