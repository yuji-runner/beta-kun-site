#!/usr/bin/env python3
"""Codex向けローカル支援ツールの統一入口。"""

import argparse
from pathlib import Path

if __package__:
    from .project_context import build_context, print_text
    from .project_diff import DEFAULT_MAX_FILES, DEFAULT_MAX_LINES, collect_diff, print_diff
    from .project_search import DEFAULT_MAX_RESULTS, print_search, search_project_report
    from .task_metrics import TaskMetrics, read_task_records, summarize_task
    from .test_runner import TARGETS, run_target
else:
    from project_context import build_context, print_text
    from project_diff import DEFAULT_MAX_FILES, DEFAULT_MAX_LINES, collect_diff, print_diff
    from project_search import DEFAULT_MAX_RESULTS, print_search, search_project_report
    from task_metrics import TaskMetrics, read_task_records, summarize_task
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
    **options,
) -> int:
    context = collect_diff(
        repo,
        query=query,
        max_lines=max_lines,
        **options,
    )

    print_diff(context)
    return 0


def run_search(
    repo: Path,
    query: str,
    limit: int,
    **options,
) -> int:
    report = search_project_report(repo, query, max_results=limit, **options)
    print_search(report)
    return 0 if report["results"] else 1


def run_finish(task_id: str, metrics: TaskMetrics) -> dict:
    before = summarize_task(task_id, metrics.metrics_file)
    finish_count_before = before["finish_count"]
    metrics.extra_fields.update({
        **before,
        "finish_count_before": finish_count_before,
        "finish_count_after": finish_count_before + 1,
        "current_finish_record_written": True,
    })
    write_result = metrics.close("success")
    after = summarize_task(task_id, metrics.metrics_file)
    current_written = any(
        item.get("timestamp_start") == metrics.timestamp_start
        and item.get("subcommand") == "finish"
        for item in read_task_records(task_id, metrics.metrics_file)
    )
    summary = {
        **before,
        "finish_count_before": finish_count_before,
        "finish_count_after": after["finish_count"],
        "current_finish_record_written": current_written,
        "metrics_write_status": "success" if write_result.success and current_written else "failed",
        "metrics_write_error_type": write_result.error_type,
    }
    print("=" * 64); print("TASK FINISH"); print("=" * 64)
    for key, value in summary.items():
        print(f"{key}: {value}")
    if finish_count_before:
        print("warning: this task_id already has a finish record")
    return summary


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
    diff_parser.add_argument("--path", action="append", dest="paths")
    diff_parser.add_argument("--staged", action="store_true")
    diff_parser.add_argument("--unstaged", action="store_true")
    diff_parser.add_argument("--untracked", action="store_true")
    diff_parser.add_argument("--include-ignored", action="store_true")
    diff_parser.add_argument("--summary-only", action="store_true")
    diff_parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)

    diff_parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
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
    search_parser.add_argument("--path", action="append", dest="paths")
    search_parser.add_argument("--glob", action="append", dest="globs")
    search_parser.add_argument("--ext", action="append", dest="extensions")
    search_parser.add_argument("--exclude", action="append", dest="excludes")
    search_parser.add_argument("--fixed-string", action="store_true")
    search_parser.add_argument("--case-sensitive", action="store_true")
    search_parser.add_argument("--include-hidden", action="store_true")

    search_parser.add_argument(
        "--max-results", "--limit",
        type=int,
        default=DEFAULT_MAX_RESULTS,
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

    subparsers.add_parser("finish", help="作業を実行せずtask終了レコードを記録")

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
            "finish": "Finish measured task",
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
                paths=args.paths,
                staged=args.staged,
                unstaged=args.unstaged,
                untracked=args.untracked,
                include_ignored=args.include_ignored,
                summary_only=args.summary_only,
                max_files=max(1, args.max_files),
            )

        elif args.command == "search":
            exit_code = run_search(
                repo,
                args.query,
                args.max_results,
                paths=args.paths,
                globs=args.globs,
                extensions=args.extensions,
                excludes=args.excludes,
                fixed_string=args.fixed_string,
                case_sensitive=args.case_sensitive,
                include_hidden=args.include_hidden,
            )

        elif args.command == "test":
            exit_code = run_tests(
                repo,
                args.target,
            )

        elif args.command == "finish":
            run_finish(metrics.task_id, metrics)
            exit_code = 0

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
    if args.command != "finish":
        metrics.close("success" if exit_code == 0 else "error")

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
