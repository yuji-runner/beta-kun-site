#!/usr/bin/env python3
"""Codex向けローカル支援ツールの統一入口。"""

import argparse
from pathlib import Path

from project_context import build_context, print_text
from project_diff import collect_diff, print_diff
from project_search import search_project
from task_metrics import TaskMetrics
from test_runner import TARGETS, run_target


DEFAULT_REPO = Path.home() / "python-study" / "my-dashboard"


def run_context(repo: Path) -> int:
    context = build_context(repo)
    print_text(context)
    return 0


def run_diff(
    repo: Path,
    query: str | None,
    max_lines: int,
) -> int:
    context = collect_diff(
        repo,
        query=query,
        max_lines=max_lines,
    )

    print_diff(context)
    return 0


def run_search(
    repo: Path,
    query: str,
    limit: int,
) -> int:
    results = search_project(
        repo,
        query,
        limit=limit,
    )

    print("=" * 64)
    print(f"PROJECT SEARCH: {query}")
    print(f"対象: {repo}")
    print("=" * 64)

    if not results:
        print("該当ファイルは見つかりませんでした。")
        return 1

    for result in results:
        print()
        print(
            f"{result['path']} "
            f"[score={result['score']}]"
        )

        if not result["matches"]:
            print("  ファイル名が一致")
            continue

        for match in result["matches"]:
            print(
                f"  L{match['line']}: "
                f"{match['text']}"
            )

    print()
    print("=" * 64)
    print(f"表示件数: {len(results)}")

    return 0


def run_tests(
    repo: Path,
    target: str,
) -> int:
    targets = (
        list(TARGETS)
        if target == "all"
        else [target]
    )

    success = True

    for target_name in targets:
        success = (
            run_target(repo, target_name)
            and success
        )

    return 0 if success else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Codex向けプロジェクト支援ツール"
    )

    parser.add_argument(
        "--repo",
        type=Path,
        default=DEFAULT_REPO,
        help="対象リポジトリ",
    )

    parser.add_argument("--task-id", help="既存の計測task_idを引き継ぐ")
    parser.add_argument("--task-description", help="計測用の短いタスク説明")
    parser.add_argument(
        "--additional-instructions",
        type=int,
        default=0,
        help="Codexへの追加指示回数",
    )
    parser.add_argument(
        "--rework-count",
        type=int,
        default=0,
        help="再修正回数",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    subparsers.add_parser(
        "context",
        help="現在のプロジェクト状況を表示",
    )

    diff_parser = subparsers.add_parser(
        "diff",
        help="現在のGit差分を確認",
    )

    diff_parser.add_argument(
        "query",
        nargs="?",
        help="ファイルパスの絞り込み語",
    )

    diff_parser.add_argument(
        "--max-lines",
        type=int,
        default=160,
        help="差分プレビューの最大行数",
    )

    search_parser = subparsers.add_parser(
        "search",
        help="関連ファイルとコードを検索",
    )

    search_parser.add_argument(
        "query",
        help="検索語",
    )

    search_parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="最大表示件数",
    )

    test_parser = subparsers.add_parser(
        "test",
        help="対象別に構文確認とテストを実行",
    )

    test_parser.add_argument(
        "target",
        choices=[*TARGETS, "all"],
        help="テスト対象",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()

    if not repo.is_dir():
        raise SystemExit(
            f"リポジトリが見つかりません: {repo}"
        )

    task_description = args.task_description
    if task_description is None:
        task_description = {
            "context": "Collect project context",
            "diff": getattr(args, "query", None) or "Collect project diff",
            "search": getattr(args, "query", None),
            "test": f"Run {getattr(args, 'target', '')} tests",
        }.get(args.command)

    metrics = TaskMetrics(
        repo=repo,
        command="codex_tools.py",
        subcommand=args.command,
        task_description=task_description,
        task_id=args.task_id,
        test_target=getattr(args, "target", None),
        additional_instruction_count=args.additional_instructions,
        rework_count=args.rework_count,
    )
    metrics.__enter__()

    try:
        if args.command == "context":
            exit_code = run_context(repo)

        elif args.command == "diff":
            exit_code = run_diff(
                repo,
                args.query,
                args.max_lines,
            )

        elif args.command == "search":
            exit_code = run_search(
                repo,
                args.query,
                args.limit,
            )

        elif args.command == "test":
            exit_code = run_tests(
                repo,
                args.target,
            )

        else:
            parser.error(
                f"未対応コマンドです: {args.command}"
            )
            return

    except Exception as error:
        metrics.test_status = "error" if args.command == "test" else None
        metrics.close("error", error=error)
        print(f"エラー: {error}")
        raise SystemExit(1)

    metrics.test_status = (
        "pass" if exit_code == 0 else "fail"
    ) if args.command == "test" else None
    metrics.close("success" if exit_code == 0 else "error")

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
