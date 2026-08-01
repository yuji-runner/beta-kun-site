#!/usr/bin/env python3
"""Codex向けにプロジェクトの現在状況を短く整理する。"""

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_REPO = Path.home() / "python-study" / "my-dashboard"
ROUTER_DIR = Path(__file__).resolve().parent
ROUTER_LOG = ROUTER_DIR / "logs" / "router_log.jsonl"

EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "captures",
}

EXCLUDED_PREFIXES = (
    "venv",
    ".venv",
    "env",
    ".env",
)

SECRET_NAMES = {
    ".env",
    "token.json",
    "credentials.json",
    "client_secret.json",
}

GENERATED_NAMES = {
    "project_context.json",
    "codex_prompt.txt",
}


def run_command(
    args: list[str],
    *,
    cwd: Path,
    timeout: int = 20,
) -> tuple[int, str, str]:
    """コマンドを実行し、終了コード・標準出力・標準エラーを返す。"""
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, "", str(error)

    return (
        result.returncode,
        result.stdout.strip(),
        result.stderr.strip(),
    )


def find_git_root(repo: Path) -> Path:
    """指定パスを含むGitリポジトリのルートを返す。"""
    code, stdout, stderr = run_command(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=repo,
    )

    if code != 0:
        raise RuntimeError(
            f"Gitリポジトリを確認できません: {stderr or repo}"
        )

    return Path(stdout).resolve()


def get_git_info(repo: Path) -> dict[str, Any]:
    """Gitの基本状態を取得する。"""
    _, branch, _ = run_command(
        ["git", "branch", "--show-current"],
        cwd=repo,
    )

    _, status, _ = run_command(
        ["git", "status", "--short"],
        cwd=repo,
    )

    _, latest_commit, _ = run_command(
        [
            "git",
            "log",
            "-1",
            "--pretty=format:%h %ad %s",
            "--date=iso",
        ],
        cwd=repo,
    )

    status_lines = [
        line
        for line in status.splitlines()
        if line.strip()
    ]

    status_summary = {
        "modified": 0,
        "deleted": 0,
        "untracked": 0,
        "other": 0,
    }

    for line in status_lines:
        code = line[:2]

        if "?" in code:
            status_summary["untracked"] += 1
        elif "D" in code:
            status_summary["deleted"] += 1
        elif "M" in code:
            status_summary["modified"] += 1
        else:
            status_summary["other"] += 1

    return {
        "branch": branch or "(detached)",
        "latest_commit": latest_commit or "取得できません",
        "dirty": bool(status_lines),
        "status_count": len(status_lines),
        "status_summary": status_summary,
        "status": status_lines,
    }


def is_safe_file(path: Path, repo: Path) -> bool:
    """秘密情報や除外ディレクトリに属さないファイルか確認する。"""
    try:
        relative = path.resolve().relative_to(repo.resolve())
    except (ValueError, OSError):
        return False

    if path.name in SECRET_NAMES:
        return False

    if path.name in GENERATED_NAMES:
        return False

    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False

    if any(
        part.startswith(EXCLUDED_PREFIXES)
        for part in relative.parts
    ):
        return False

    try:
        return path.is_file()
    except OSError:
        return False


def iter_project_files(repo: Path):
    """除外ディレクトリへ入らず、プロジェクト内のファイルを列挙する。"""
    for root, dir_names, file_names in os.walk(repo):
        root_path = Path(root)

        dir_names[:] = [
            name
            for name in dir_names
            if (
                name not in EXCLUDED_PARTS
                and not name.startswith(EXCLUDED_PREFIXES)
            )
        ]

        for file_name in file_names:
            path = root_path / file_name

            if is_safe_file(path, repo):
                yield path


def collect_recent_files(
    repo: Path,
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """最近更新された主要なテキストファイルを取得する。"""
    allowed_suffixes = {
        ".py",
        ".html",
        ".js",
        ".css",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".md",
        ".txt",
    }

    candidates: list[tuple[float, Path]] = []

    for path in iter_project_files(repo):
        if path.suffix.lower() not in allowed_suffixes:
            continue

        try:
            modified = path.stat().st_mtime
        except OSError:
            continue

        candidates.append((modified, path))

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    result = []

    for modified, path in candidates[:limit]:
        result.append({
            "path": str(path.relative_to(repo)),
            "modified": datetime.fromtimestamp(
                modified
            ).astimezone().isoformat(timespec="seconds"),
        })

    return result


def collect_key_files(repo: Path) -> list[str]:
    """Codexが最初に確認しやすい主要ファイルを抽出する。"""
    preferred_names = {
        "app.py",
        "router.py",
        "config.py",
        "logger.py",
        "log_summary.py",
        "project_context.py",
        "project_search.py",
        "test_runner.py",
        "codex_tools.py",
        "codex_prepare.py",
        "requirements.txt",
        "pyproject.toml",
        "README.md",
    }

    result = []

    for path in iter_project_files(repo):
        if path.name not in preferred_names:
            continue

        result.append(str(path.relative_to(repo)))

    return sorted(result)


def collect_test_files(
    repo: Path,
    *,
    limit: int = 30,
) -> list[str]:
    """テスト候補ファイルを取得する。"""
    result = []

    for path in iter_project_files(repo):
        name = path.name.lower()

        if path.suffix.lower() != ".py":
            continue

        if (
            name.startswith("test_")
            or name.endswith("_test.py")
            or name.endswith("_tests.py")
            or "smoke" in name
        ):
            result.append(str(path.relative_to(repo)))

    return sorted(result)[:limit]


def collect_providers() -> list[str]:
    """βRouterに存在するProvider名を取得する。"""
    providers_dir = ROUTER_DIR / "providers"

    if not providers_dir.exists():
        return []

    result = []

    for path in providers_dir.glob("*.py"):
        if path.name in {
            "__init__.py",
            "base.py",
        }:
            continue

        result.append(path.stem)

    return sorted(result)


def collect_router_logs(
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """βRouterの直近ログを本文なしで取得する。"""
    if not ROUTER_LOG.exists():
        return []

    records = []

    try:
        lines = ROUTER_LOG.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
    except OSError:
        return []

    for line in reversed(lines):
        if not line.strip():
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not isinstance(record, dict):
            continue

        records.append({
            "timestamp": record.get("timestamp"),
            "status": record.get("status"),
            "task_type": record.get("task_type"),
            "requested_provider": record.get(
                "requested_provider"
            ),
            "provider_used": record.get("provider_used"),
            "fallback": record.get("fallback"),
            "elapsed_sec": record.get("elapsed_sec"),
        })

        if len(records) >= limit:
            break

    return records


def infer_commands(repo: Path) -> list[str]:
    """存在するファイルから有用な確認コマンドを作る。"""
    commands = [
        "git status --short",
        "git diff --stat",
    ]

    app_py = repo / "app.py"

    if app_py.exists():
        commands.extend([
            "python3 -m py_compile app.py",
            "python3 app.py",
        ])

    router_py = (
        repo
        / "beta-kun-site"
        / "beta_router"
        / "router.py"
    )

    if router_py.exists():
        commands.extend([
            (
                "python3 -m py_compile "
                "beta-kun-site/beta_router/router.py"
            ),
            (
                "python3 beta-kun-site/beta_router/"
                "log_summary.py --today"
            ),
        ])

    return commands


def build_context(repo: Path) -> dict[str, Any]:
    """Codex向けコンテキストを辞書形式で作成する。"""
    git_root = find_git_root(repo)
    git_info = get_git_info(git_root)

    return {
        "generated_at": (
            datetime.now()
            .astimezone()
            .isoformat(timespec="seconds")
        ),
        "repository": str(git_root),
        "git": git_info,
        "recent_files": collect_recent_files(git_root),
        "key_files": collect_key_files(git_root),
        "test_files": collect_test_files(git_root),
        "beta_router": {
            "path": str(ROUTER_DIR),
            "providers": collect_providers(),
            "recent_logs": collect_router_logs(),
        },
        "useful_commands": infer_commands(git_root),
        "safety": [
            "既存の未コミット変更を消さない",
            ".env・APIキー・認証情報を表示またはコミットしない",
            "変更前に関連ファイルとgit diffを確認する",
            "必要最小限の変更にする",
            "編集後は構文確認と関連テストを実行する",
        ],
    }


def print_text(context: dict[str, Any]) -> None:
    """人間・Codex向けの短いテキストで表示する。"""
    git = context["git"]
    router = context["beta_router"]

    print("=" * 64)
    print("PROJECT CONTEXT")
    print("=" * 64)
    print(f"生成日時       : {context['generated_at']}")
    print(f"リポジトリ     : {context['repository']}")
    print(f"ブランチ       : {git['branch']}")
    print(f"最新コミット   : {git['latest_commit']}")
    print(
        f"未コミット変更 : "
        f"{'あり' if git['dirty'] else 'なし'}"
    )

    print("-" * 64)
    print("git status")

    if git["status"]:
        summary = git["status_summary"]

        print(
            f"  合計 {git['status_count']}件 "
            f"(変更 {summary['modified']} / "
            f"削除 {summary['deleted']} / "
            f"未追跡 {summary['untracked']} / "
            f"その他 {summary['other']})"
        )

        preview_limit = 30

        for line in git["status"][:preview_limit]:
            print(f"  {line}")

        omitted = len(git["status"]) - preview_limit

        if omitted > 0:
            print(f"  ... ほか {omitted}件")
    else:
        print("  変更なし")

    print("-" * 64)
    print("最近変更されたファイル")

    for item in context["recent_files"]:
        print(
            f"  {item['path']} "
            f"({item['modified']})"
        )

    print("-" * 64)
    print("主要ファイル")

    for path in context["key_files"]:
        print(f"  {path}")

    print("-" * 64)
    print("テスト候補")

    if context["test_files"]:
        for path in context["test_files"]:
            print(f"  {path}")
    else:
        print("  見つかりません")

    print("-" * 64)
    print("βRouter")

    print(f"  パス: {router['path']}")
    print(
        "  Provider: "
        + (
            ", ".join(router["providers"])
            if router["providers"]
            else "なし"
        )
    )

    print("  直近ログ:")

    if router["recent_logs"]:
        for record in router["recent_logs"]:
            print(
                "   - "
                f"{record.get('timestamp')} "
                f"{record.get('status')} "
                f"{record.get('task_type')} "
                f"{record.get('provider_used')} "
                f"fallback={record.get('fallback')}"
            )
    else:
        print("   - なし")

    print("-" * 64)
    print("有用なコマンド")

    for command in context["useful_commands"]:
        print(f"  {command}")

    print("-" * 64)
    print("安全上の注意")

    for item in context["safety"]:
        print(f"  - {item}")

    print("=" * 64)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Codex向けプロジェクト状況を表示します。"
    )

    parser.add_argument(
        "--repo",
        type=Path,
        default=DEFAULT_REPO,
        help="確認するGitリポジトリまたはその配下",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力する",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = args.repo.expanduser().resolve()

    try:
        context = build_context(repo)
    except RuntimeError as error:
        print(f"エラー: {error}")
        raise SystemExit(1)

    if args.json:
        print(
            json.dumps(
                context,
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    print_text(context)


if __name__ == "__main__":
    main()
