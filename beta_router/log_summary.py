#!/usr/bin/env python3

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any


LOG_FILE = Path(__file__).parent / "logs" / "router_log.jsonl"


def load_logs(log_file: Path = LOG_FILE) -> tuple[list[dict], int]:
    """JSONLログを読み込み、正常レコードと不正行数を返す。"""
    records: list[dict] = []
    invalid_lines = 0

    if not log_file.exists():
        raise FileNotFoundError(
            f"ログファイルが見つかりません: {log_file}"
        )

    with log_file.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                invalid_lines += 1
                continue

            if isinstance(record, dict):
                records.append(record)
            else:
                invalid_lines += 1

    return records, invalid_lines


def percentage(value: int, total: int) -> float:
    """割合を百分率で返す。"""
    if total == 0:
        return 0.0

    return value / total * 100


def parse_timestamp(value: object) -> datetime | None:
    """ISO形式のtimestampをdatetimeへ変換する。"""
    if not isinstance(value, str):
        return None

    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return None

    if timestamp.tzinfo is None:
        timestamp = timestamp.astimezone()

    return timestamp


def filter_records(
    records: list[dict],
    *,
    today: bool = False,
    last_days: int | None = None,
) -> tuple[list[dict], str]:
    """指定された期間に合わせてログを絞り込む。"""
    now = datetime.now().astimezone()

    if today:
        target_date = now.date()

        filtered = [
            record
            for record in records
            if (
                (timestamp := parse_timestamp(record.get("timestamp")))
                is not None
                and timestamp.astimezone().date() == target_date
            )
        ]

        return filtered, f"今日（{target_date.isoformat()}）"

    if last_days is not None:
        if last_days < 1:
            raise ValueError(
                "last_daysには1以上の日数を指定してください。"
            )

        start = now - timedelta(days=last_days)

        filtered = [
            record
            for record in records
            if (
                (timestamp := parse_timestamp(record.get("timestamp")))
                is not None
                and timestamp.astimezone() >= start
            )
        ]

        return filtered, f"直近{last_days}日"

    return records, "全期間"


def build_summary(
    *,
    today: bool = False,
    last_days: int | None = None,
    log_file: Path = LOG_FILE,
) -> dict[str, Any]:
    """
    βRouterログを集計し、辞書形式で返す。

    CLIだけでなく、Flaskなど外部Pythonコードからも利用できる。
    """
    records, invalid_lines = load_logs(log_file)

    records, period_label = filter_records(
        records,
        today=today,
        last_days=last_days,
    )

    total = len(records)

    status_counts = Counter(
        record.get("status", "unknown")
        for record in records
    )

    provider_counts = Counter(
        record.get("provider_used")
        for record in records
        if record.get("provider_used")
    )

    task_counts = Counter(
        record.get("task_type", "unknown")
        for record in records
    )

    success_count = status_counts.get("success", 0)
    error_count = status_counts.get("error", 0)

    ollama_count = provider_counts.get("ollama", 0)
    groq_count = provider_counts.get("groq", 0)
    nvidia_count = provider_counts.get("nvidia", 0)

    fallback_records = [
        record
        for record in records
        if record.get("fallback") is True
    ]

    fallback_count = len(fallback_records)

    fallback_success_count = sum(
        1
        for record in fallback_records
        if record.get("status") == "success"
    )

    fallback_error_count = sum(
        1
        for record in fallback_records
        if record.get("status") == "error"
    )

    elapsed_times = [
        float(record["elapsed_sec"])
        for record in records
        if isinstance(record.get("elapsed_sec"), (int, float))
    ]

    average_elapsed = (
        mean(elapsed_times)
        if elapsed_times
        else 0.0
    )

    provider_execution_count = sum(provider_counts.values())

    success_rate = percentage(success_count, total)
    fallback_rate = percentage(fallback_count, total)
    fallback_success_rate = percentage(
        fallback_success_count,
        fallback_count,
    )

    local_rate = percentage(
        ollama_count,
        provider_execution_count,
    )

    cloud_provider_count = sum(
        count
        for provider, count in provider_counts.items()
        if provider != "ollama"
    )

    cloud_rate = percentage(
        cloud_provider_count,
        provider_execution_count,
    )

    provider_names = sorted(
        {
            record.get("requested_provider")
            for record in records
            if record.get("requested_provider")
        }
        | set(provider_counts.keys())
    )

    provider_stats: dict[str, dict[str, int | float]] = {}

    for provider in provider_names:
        provider_attempts = [
            record
            for record in records
            if record.get("requested_provider") == provider
            or record.get("provider_used") == provider
        ]

        provider_successes = sum(
            1
            for record in provider_attempts
            if record.get("provider_used") == provider
            and record.get("status") == "success"
        )

        provider_failures = (
            len(provider_attempts) - provider_successes
        )

        provider_times = [
            float(record["elapsed_sec"])
            for record in records
            if record.get("provider_used") == provider
            and isinstance(
                record.get("elapsed_sec"),
                (int, float),
            )
        ]

        provider_average = (
            mean(provider_times)
            if provider_times
            else 0.0
        )

        provider_stats[provider] = {
            "attempts": len(provider_attempts),
            "used": provider_counts.get(provider, 0),
            "success": provider_successes,
            "error": provider_failures,
            "success_rate": round(
                percentage(
                    provider_successes,
                    len(provider_attempts),
                ),
                1,
            ),
            "average_elapsed_sec": round(
                provider_average,
                3,
            ),
        }

    return {
        "period": period_label,
        "log_file": str(log_file),
        "total": total,
        "success": success_count,
        "error": error_count,
        "success_rate": round(success_rate, 1),
        "providers": {
            provider: {
                "used": count,
                "rate": round(
                    percentage(
                        count,
                        provider_execution_count,
                    ),
                    1,
                ),
            }
            for provider, count
            in sorted(provider_counts.items())
        },
        "fallback": {
            "count": fallback_count,
            "success": fallback_success_count,
            "error": fallback_error_count,
            "rate": round(fallback_rate, 1),
            "rescue_success_rate": round(
                fallback_success_rate,
                1,
            ),
        },
        "performance": {
            "average_elapsed_sec": round(
                average_elapsed,
                3,
            ),
            "local_rate": round(local_rate, 1),
            "cloud_rate": round(cloud_rate, 1),
        },
        "task_types": dict(sorted(task_counts.items())),
        "provider_stats": provider_stats,
        "invalid_lines": invalid_lines,
    }


def print_text_summary(summary: dict[str, Any]) -> None:
    """集計結果を人間向け形式で表示する。"""
    print("=" * 48)
    print("βRouter ログ集計")
    print("=" * 48)
    print(f"ログファイル       : {summary['log_file']}")
    print(f"集計期間           : {summary['period']}")
    print(f"総実行回数         : {summary['total']}")
    print(f"成功数             : {summary['success']}")
    print(f"失敗数             : {summary['error']}")
    print(f"成功率             : {summary['success_rate']:.1f}%")
    print("-" * 48)

    providers = summary["providers"]
    fallback = summary["fallback"]
    performance = summary["performance"]

    provider_labels = {
        "ollama": "Ollama",
        "groq": "Groq",
        "nvidia": "NVIDIA",
    }

    for provider, stats in providers.items():
        label = provider_labels.get(
            provider,
            provider.capitalize(),
        )

        print(
            f"{label + '利用回数':<19}: "
            f"{stats['used']} "
            f"({stats['rate']:.1f}%)"
        )
    print(f"フォールバック回数 : {fallback['count']}")
    print(f"フォールバック成功 : {fallback['success']}")
    print(f"フォールバック失敗 : {fallback['error']}")
    print(f"フォールバック率   : {fallback['rate']:.1f}%")
    print(
        f"救済成功率         : "
        f"{fallback['rescue_success_rate']:.1f}%"
    )
    print("-" * 48)
    print(
        f"平均応答時間       : "
        f"{performance['average_elapsed_sec']:.3f}秒"
    )
    print(
        f"ローカル処理率     : "
        f"{performance['local_rate']:.1f}%"
    )
    print(
        f"クラウド利用率     : "
        f"{performance['cloud_rate']:.1f}%"
    )
    print("-" * 48)
    print("タスク種類別")

    if summary["task_types"]:
        for task_type, count in summary["task_types"].items():
            print(f"  {task_type:<14}: {count}")
    else:
        print("  データなし")

    print("-" * 48)
    print("Provider別成功率")

    if summary["provider_stats"]:
        for provider, stats in summary["provider_stats"].items():
            print(
                f"  {provider:<14}: "
                f"成功 {stats['success']} / "
                f"失敗 {stats['error']} / "
                f"成功率 {stats['success_rate']:.1f}%"
            )
    else:
        print("  データなし")

    print("-" * 48)
    print("Provider別平均応答時間")

    provider_time_found = False

    for provider, stats in summary["provider_stats"].items():
        if stats["used"] == 0:
            continue

        provider_time_found = True

        print(
            f"  {provider:<14}: "
            f"{stats['average_elapsed_sec']:.3f}秒 "
            f"（{stats['used']}回）"
        )

    if not provider_time_found:
        print("  データなし")

    if summary["invalid_lines"]:
        print("-" * 48)
        print(
            f"読み飛ばした行     : "
            f"{summary['invalid_lines']}"
        )

    print("=" * 48)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="βRouterのJSONLログを集計します。"
    )

    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "--today",
        action="store_true",
        help="今日のログだけを集計する",
    )

    group.add_argument(
        "--last",
        type=int,
        metavar="DAYS",
        help="直近DAYS日分のログを集計する",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="集計結果をJSON形式で出力する",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        summary = build_summary(
            today=args.today,
            last_days=args.last,
        )
    except (FileNotFoundError, ValueError) as error:
        print(f"エラー: {error}")
        raise SystemExit(1)

    if args.json:
        print(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    print_text_summary(summary)


if __name__ == "__main__":
    main()
