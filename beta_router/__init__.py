"""βRouter 公開API。"""

from .router import BetaRouter, ChatResult, RouteDecision


_default_router: BetaRouter | None = None


def get_router() -> BetaRouter:
    """共有のBetaRouterインスタンスを返す。"""
    global _default_router

    if _default_router is None:
        _default_router = BetaRouter()

    return _default_router


def ask(
    prompt: str,
    provider: str = "auto",
    routing_text: str | None = None,
) -> str:
    """βRouterを通してAIへ質問する。"""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("promptを入力してください。")

    return get_router().ask(
        prompt=prompt.strip(),
        provider=provider,
        routing_text=(
            routing_text.strip()
            if isinstance(routing_text, str)
            else None
        ),
    )


__all__ = [
    "ask",
    "get_router",
    "BetaRouter",
    "ChatResult",
    "RouteDecision",
]
