#!/usr/bin/env python3
"""Codex向けの軽量テスト実行ツール。"""

import argparse
import subprocess
from pathlib import Path


DEFAULT_REPO = Path.home() / "python-study" / "my-dashboard"

TARGETS = {
    "router": {
        "files": [
            "beta-kun-site/beta_router/router.py",
            "beta-kun-site/beta_router/config.py",
            "beta-kun-site/beta_router/logger.py",
            "beta-kun-site/beta_router/log_summary.py",
            "beta-kun-site/beta_router/project_context.py",
            "beta-kun-site/beta_router/project_search.py",
            "beta-kun-site/beta_router/project_diff.py",
            "beta-kun-site/beta_router/test_runner.py",
            "beta-kun-site/beta_router/codex_tools.py",
            "beta-kun-site/beta_router/providers/base.py",
            "beta-kun-site/beta_router/providers/groq.py",
            "beta-kun-site/beta_router/providers/ollama.py",
            "beta-kun-site/beta_router/providers/nvidia.py",
        ],
        "commands": [
            [
                "python3",
                "beta-kun-site/beta_router/log_summary.py",
                "--today",
            ],
        ],
    },
    "app": {
        "files": [
            "app.py",
        ],
        "commands": [],
    },
    "search-ui": {
        "files": [
            "beta-kun-site/search_ui_contract_tests.py",
        ],
        "commands": [
            [
                "python3",
                "beta-kun-site/search_ui_contract_tests.py",
            ],
        ],
    },
}


def run_command(
    command: list[str],
    *,
    cwd: Path,
) -> tuple[bool, str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
    )

    output = "\n".join(
        part.strip()
        for part in (
            result.stdout,
            result.stderr,
        )
        if part.strip()
    )

    return result.returncode == 0, output


def run_target(
    repo: Path,
    target_name: str,
) -> bool:
    target = TARGETS[target_name]
    success = True

    print("=" * 64)
    print(f"TEST TARGET: {target_name}")
    print("=" * 64)

    existing_files = []

    for relative in target["files"]:
        path = repo / relative

        if path.exists():
            existing_files.append(relative)
        else:
            print(f"SKIP missing: {relative}")

    if existing_files:
        command = [
            "python3",
            "-m",
            "py_compile",
            *existing_files,
        ]

        print()
        print("$", " ".join(command))

        ok, output = run_command(
            command,
            cwd=repo,
        )

        print("PASS" if ok else "FAIL")

        if output:
            print(output)

        success = success and ok

    for command in target["commands"]:
        print()
        print("$", " ".join(command))

        ok, output = run_command(
            command,
            cwd=repo,
        )

        print("PASS" if ok else "FAIL")

        if output:
            print(output)

        success = success and ok

    print()
    print("=" * 64)
    print(
        f"RESULT: {'PASS' if success else 'FAIL'}"
    )

    return success


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="対象別に構文確認と関連テストを実行します。"
    )

    parser.add_argument(
        "target",
        choices=[*TARGETS, "all"],
        help="テスト対象",
    )

    parser.add_argument(
        "--repo",
        type=Path,
        default=DEFAULT_REPO,
        help="対象リポジトリ",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = args.repo.expanduser().resolve()

    if not repo.is_dir():
        raise SystemExit(
            f"リポジトリが見つかりません: {repo}"
        )

    targets = (
        list(TARGETS)
        if args.target == "all"
        else [args.target]
    )

    all_success = True

    for target_name in targets:
        result = run_target(
            repo,
            target_name,
        )

        all_success = all_success and result

    raise SystemExit(0 if all_success else 1)


if __name__ == "__main__":
    main()
