#!/usr/bin/env python3
"""Codex向けの軽量テスト実行ツール。"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


DEFAULT_REPO = Path.home() / "python-study" / "my-dashboard"

TARGETS = {
    "router": {
        "base": "beta_site",
        "files": [
            "beta_router/__init__.py",
            "beta_router/router.py",
            "beta_router/config.py",
            "beta_router/logger.py",
            "beta_router/log_summary.py",
            "beta_router/project_context.py",
            "beta_router/project_search.py",
            "beta_router/project_diff.py",
            "beta_router/test_runner.py",
            "beta_router/codex_tools.py",
            "beta_router/codex_prepare.py",
            "beta_router/task_metrics.py",
            "beta_router/task_metrics_tests.py",
            "beta_router/project_tools_tests.py",
            "beta_router/providers/__init__.py",
            "beta_router/providers/base.py",
            "beta_router/providers/groq.py",
            "beta_router/providers/ollama.py",
            "beta_router/providers/nvidia.py",
        ],
        "commands": [
            ("beta_router/task_metrics_tests.py",),
            ("beta_router/log_summary.py", "--today"),
        ],
    },
    "app": {
        "base": "repo",
        "files": [
            "app.py",
        ],
        "commands": [],
    },
    "search-ui": {
        "base": "beta_site",
        "files": [
            "search_ui_contract_tests.py",
        ],
        "commands": [
            ("search_ui_contract_tests.py",),
        ],
    },
}


def find_beta_site_root(repo: Path) -> Path:
    """Resolve βRouter whether repo is the parent or beta-kun-site itself."""
    if (repo / "beta_router").is_dir():
        return repo

    nested = repo / "beta-kun-site"
    if (nested / "beta_router").is_dir():
        return nested

    return repo


def run_command(
    command: list[str],
    *,
    cwd: Path,
) -> tuple[bool, str]:
    environment = os.environ.copy()
    environment.setdefault(
        "PYTHONPYCACHEPREFIX",
        str(Path(tempfile.gettempdir()) / "beta_router_pycache"),
    )

    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=environment,
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
    beta_site_root = find_beta_site_root(repo)
    base = beta_site_root if target["base"] == "beta_site" else repo
    success = True

    print("=" * 64)
    print(f"TEST TARGET: {target_name}")
    print("=" * 64)

    existing_files = []

    for relative in target["files"]:
        path = base / relative

        if path.exists():
            existing_files.append(str(path))
        else:
            print(f"SKIP missing: {path}")

    if existing_files:
        command = [
            sys.executable,
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

    for script, *arguments in target["commands"]:
        command = [
            sys.executable,
            str(base / script),
            *arguments,
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
