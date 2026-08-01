import argparse
import time
from dataclasses import dataclass
from pathlib import Path

import requests

try:
    # beta_routerパッケージとしてimportする場合
    from .logger import write_log
    from .task_metrics import TaskMetrics, current_metrics
    from .providers.groq import GroqProvider
    from .providers.nvidia import NvidiaProvider
    from .providers.ollama import OllamaProvider
except ImportError:
    # router.pyを直接CLI実行する場合
    from logger import write_log
    from task_metrics import TaskMetrics, current_metrics
    from providers.groq import GroqProvider
    from providers.nvidia import NvidiaProvider
    from providers.ollama import OllamaProvider


@dataclass
class RouteDecision:
    provider: str
    reason: str
    task_type: str


@dataclass
class ChatResult:
    answer: str
    provider_used: str
    fallback: bool


class BetaRouter:
    def __init__(self):
        self.providers = {
            "ollama": OllamaProvider(),
            "groq": GroqProvider(),
            "nvidia": NvidiaProvider(),
        }

    def decide_route(self, prompt: str) -> RouteDecision:
        normalized = prompt.lower()

        code_keywords = (
            "コード解析",
            "コード分析",
            "実装計画",
            "修正方針",
            "変更ファイル",
            "影響範囲",
            "テスト計画",
            "テスト項目",
            "リファクタリング",
            "リファクタ",
            "デバッグ",
            "バグ修正",
            "pythonコード",
            "javascriptコード",
            "htmlコード",
            "flask",
            "関数を修正",
            "実装案",
            "codex向け",
            "codexに渡す",
        )

        groq_keywords = (
            "長文",
            "詳しく",
            "比較",
            "レビュー",
            "検討",
            "分析",
            "論文",
            "要約して",
            "改善案",
            "設計",
            "複雑",
        )

        local_keywords = (
            "患者",
            "個人情報",
            "氏名",
            "住所",
            "電話番号",
            "ローカル限定",
            "外部送信禁止",
            "外部送信せず",
            "機密",
        )

        simple_keywords = (
            "分類",
            "整形",
            "json",
            "一文",
            "短く",
            "箇条書き",
            "誤字",
            "変換",
        )

        if any(keyword in normalized for keyword in local_keywords):
            return RouteDecision(
                provider="ollama",
                reason=(
                    "機密情報を含む可能性があるため"
                    "ローカル処理を優先"
                ),
                task_type="sensitive",
            )

        if any(keyword in normalized for keyword in code_keywords):
            return RouteDecision(
                provider="nvidia",
                reason=(
                    "コード分析・実装計画・テスト設計として"
                    "NVIDIAコードモデルを選択"
                ),
                task_type="code_analysis",
            )

        if any(keyword in normalized for keyword in groq_keywords):
            return RouteDecision(
                provider="groq",
                reason=(
                    "分析・長文・レビュー系の処理として"
                    "高速クラウドモデルを選択"
                ),
                task_type="analysis",
            )

        if any(keyword in normalized for keyword in simple_keywords):
            return RouteDecision(
                provider="ollama",
                reason=(
                    "分類・整形などの軽量処理として"
                    "ローカルモデルを選択"
                ),
                task_type="lightweight",
            )

        return RouteDecision(
            provider="ollama",
            reason=(
                "明確な重処理条件がないため、"
                "費用のかからないローカルモデルを優先"
            ),
            task_type="general",
        )

    def ask(
        self,
        prompt: str,
        provider: str = "auto",
        routing_text: str | None = None,
    ) -> str:
        start_time = time.perf_counter()

        task_type = "manual"
        route_reason = "ユーザーがproviderを手動指定"
        requested_provider = provider
        provider_used = ""
        fallback = False
        metrics = current_metrics()
        owns_metrics = metrics is None
        if metrics is None:
            metrics = TaskMetrics(
                repo=Path(__file__).resolve().parents[2],
                command="router.py",
                subcommand="ask",
                task_description="BetaRouter provider request",
                provider_purpose="routing",
            )
            metrics.__enter__()

        try:
            if provider == "auto":
                decision = self.decide_route(
                    routing_text
                    if routing_text is not None
                    else prompt
                )

                task_type = decision.task_type
                route_reason = decision.reason
                requested_provider = decision.provider
                metrics.provider_purpose = decision.task_type

                print(
                    f"→ Auto選択: "
                    f"{decision.provider.capitalize()}"
                )
                print(f"  種類: {decision.task_type}")
                print(f"  理由: {decision.reason}")

                result = self._chat_with_fallback(
                    prompt=prompt,
                    primary_provider=decision.provider,
                    allow_cloud_fallback=(
                        decision.task_type != "sensitive"
                    ),
                )

            else:
                if provider not in self.providers:
                    available = ", ".join(
                        ["auto", *self.providers]
                    )
                    raise ValueError(
                        f"未対応のproviderです: {provider} "
                        f"利用可能: {available}"
                    )

                print(
                    f"→ 手動選択: "
                    f"{provider.capitalize()}"
                )

                answer = self._provider_chat(provider, prompt, metrics)

                result = ChatResult(
                    answer=answer,
                    provider_used=provider,
                    fallback=False,
                )

            provider_used = result.provider_used
            fallback = result.fallback

            elapsed_sec = round(
                time.perf_counter() - start_time,
                3,
            )

            write_log(
                {
                    "status": "success",
                    "task_type": task_type,
                    "requested_provider": requested_provider,
                    "provider_used": provider_used,
                    "fallback": fallback,
                    "route_reason": route_reason,
                    "elapsed_sec": elapsed_sec,
                    "prompt_length": len(prompt),
                    "response_length": len(result.answer),
                }
            )

            if owns_metrics:
                metrics.close("success")

            return result.answer

        except Exception as exc:
            elapsed_sec = round(
                time.perf_counter() - start_time,
                3,
            )

            write_log(
                {
                    "status": "error",
                    "task_type": task_type,
                    "requested_provider": requested_provider,
                    "provider_used": provider_used or None,
                    "fallback": fallback,
                    "route_reason": route_reason,
                    "elapsed_sec": elapsed_sec,
                    "prompt_length": len(prompt),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

            if owns_metrics:
                metrics.close("error", error=exc)

            raise

    def _provider_chat(
        self,
        provider: str,
        prompt: str,
        metrics: TaskMetrics,
    ) -> str:
        metrics.provider_call(provider, metrics.provider_purpose)
        metrics.prompt_length = len(prompt)
        return self.providers[provider].chat(prompt)

    def _chat_with_fallback(
        self,
        prompt: str,
        primary_provider: str,
        allow_cloud_fallback: bool = True,
    ) -> ChatResult:
        fallback_map = {
            "ollama": "groq",
            "groq": "nvidia",
            "nvidia": "groq",
        }

        fallback_provider = fallback_map.get(primary_provider)

        if fallback_provider is None:
            raise ValueError(
                f"フォールバック先が未定義です: {primary_provider}"
            )

        try:
            metrics = current_metrics()
            if metrics is None:
                raise RuntimeError("計測セッションがありません。")
            answer = self._provider_chat(
                primary_provider,
                prompt,
                metrics,
            )

            return ChatResult(
                answer=answer,
                provider_used=primary_provider,
                fallback=False,
            )

        except (
            requests.ConnectionError,
            requests.Timeout,
            requests.HTTPError,
            RuntimeError,
        ) as exc:
            print(f"⚠ {primary_provider}失敗: {exc}")

            if (
                primary_provider == "ollama"
                and not allow_cloud_fallback
            ):
                raise RuntimeError(
                    "機密情報を含む可能性があるため、"
                    "クラウドAIへのフォールバックを"
                    "中止しました。"
                ) from exc

            print(
                f"→ {fallback_provider.capitalize()}へ"
                "フォールバック"
            )

            metrics.fallback_count += 1

            answer = self._provider_chat(
                fallback_provider,
                prompt,
                metrics,
            )

            return ChatResult(
                answer=answer,
                provider_used=fallback_provider,
                fallback=True,
            )


def parse_args():
    parser = argparse.ArgumentParser(
        description="βRouter CLI",
    )

    parser.add_argument(
        "prompt",
        nargs="?",
        default=(
            "βRouterの役割を一文で"
            "説明してください。"
        ),
        help="AIへ送る質問",
    )

    parser.add_argument(
        "--provider",
        choices=["auto", "ollama", "groq", "nvidia"],
        default="auto",
        help="利用するAIプロバイダー",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    router = BetaRouter()

    try:
        answer = router.ask(
            prompt=args.prompt,
            provider=args.provider,
        )
    except Exception as exc:
        print()
        print(f"エラー: {exc}")
        raise SystemExit(1)

    print()
    print(answer)
