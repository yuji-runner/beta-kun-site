#!/usr/bin/env python3
"""Codex向けのGit差分確認ツール。"""

import argparse
import subprocess
from pathlib import Path


DEFAULT_REPO = Path.home() / "python-study" / "my-dashboard"

SECRET_NAMES = {
    ".env",
    "token.json",
    "credentials.json",
    "client_secret.json",
}

EXCLUDED_NAMES = {
    "project_context.json",
    "codex_prompt.txt",
    "nano",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pid",
}

EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
}


def run_git(
    repo: Path,
    *args: str,
) -> tuple[int, str, str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
    )

    return (
        result.returncode,
        result.stdout.strip(),
        result.stderr.strip(),
    )


def is_safe_relative_path(relative: str) -> bool:
    path = Path(relative)

    if path.name in SECRET_NAMES:
        return False

    if path.name in EXCLUDED_NAMES:
        return False

    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False

    if (
        ".bak" in path.name
        or path.name.endswith("~")
        or path.name.startswith(".#")
    ):
        return False

    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False

    return True


def matches_query(
    relative: str,
    query: str | None,
) -> bool:
    if not query:
        return True

    return query.lower() in relative.lower()


def parse_name_status(output: str) -> list[dict[str, str]]:
    result = []

    for line in output.splitlines():
        if not line.strip():
            continue

        parts = line.split("\t")

        if len(parts) < 2:
            continue

        status = parts[0]
        relative = parts[-1]

        if not is_safe_relative_path(relative):
            continue

        result.append({
            "status": status,
            "path": relative,
        })

    return result


def collect_untracked(repo: Path) -> list[str]:
    code, stdout, _ = run_git(
        repo,
        "ls-files",
        "--others",
        "--exclude-standard",
    )

    if code != 0:
        return []

    return [
        line
        for line in stdout.splitlines()
        if (
            line.strip()
            and is_safe_relative_path(line.strip())
        )
    ]


def collect_numstat(
    repo: Path,
    *,
    cached: bool,
) -> dict[str, dict[str, int | str]]:
    args = ["diff", "--numstat"]

    if cached:
        args.append("--cached")

    code, stdout, _ = run_git(repo, *args)

    if code != 0:
        return {}

    result: dict[str, dict[str, int | str]] = {}

    for line in stdout.splitlines():
        parts = line.split("\t")

        if len(parts) < 3:
            continue

        added_raw, deleted_raw, relative = parts[0], parts[1], parts[-1]

        if not is_safe_relative_path(relative):
            continue

        added: int | str = (
            int(added_raw)
            if added_raw.isdigit()
            else added_raw
        )
        deleted: int | str = (
            int(deleted_raw)
            if deleted_raw.isdigit()
            else deleted_raw
        )

        result[relative] = {
            "added": added,
            "deleted": deleted,
        }

    return result


def collect_diff(
    repo: Path,
    *,
    query: str | None = None,
    max_lines: int = 160,
) -> dict:
    _, branch, _ = run_git(
        repo,
        "branch",
        "--show-current",
    )

    _, latest_commit, _ = run_git(
        repo,
        "log",
        "-1",
        "--pretty=format:%h %ad %s",
        "--date=iso",
    )

    _, unstaged_raw, _ = run_git(
        repo,
        "diff",
        "--name-status",
    )

    _, staged_raw, _ = run_git(
        repo,
        "diff",
        "--cached",
        "--name-status",
    )

    unstaged = [
        item
        for item in parse_name_status(unstaged_raw)
        if matches_query(item["path"], query)
    ]

    staged = [
        item
        for item in parse_name_status(staged_raw)
        if matches_query(item["path"], query)
    ]

    untracked = [
        relative
        for relative in collect_untracked(repo)
        if matches_query(relative, query)
    ]

    unstaged_numstat = collect_numstat(
        repo,
        cached=False,
    )
    staged_numstat = collect_numstat(
        repo,
        cached=True,
    )

    diff_paths = [
        item["path"]
        for item in [*staged, *unstaged]
    ]

    diff_args = ["diff", "--no-ext-diff", "--unified=2"]

    if query:
        if diff_paths:
            diff_args.extend(
                ["--", *dict.fromkeys(diff_paths)]
            )
            _, diff_text, _ = run_git(repo, *diff_args)
        else:
            # 絞り込み対象が0件なら、全リポジトリの差分を
            # 誤って表示しない。
            diff_text = ""
    else:
        _, diff_text, _ = run_git(repo, *diff_args)

    diff_lines = diff_text.splitlines()
    diff_truncated = len(diff_lines) > max_lines

    return {
        "repository": str(repo),
        "branch": branch or "(detached)",
        "latest_commit": latest_commit or "取得できません",
        "query": query,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "staged_numstat": staged_numstat,
        "unstaged_numstat": unstaged_numstat,
        "diff_preview": diff_lines[:max_lines],
        "diff_truncated": diff_truncated,
        "diff_total_lines": len(diff_lines),
    }


def print_file_group(
    title: str,
    items: list[dict[str, str]],
    numstat: dict[str, dict[str, int | str]],
) -> None:
    print(title)

    if not items:
        print("  なし")
        return

    for item in items:
        relative = item["path"]
        stats = numstat.get(relative, {})

        added = stats.get("added", "-")
        deleted = stats.get("deleted", "-")

        print(
            f"  {item['status']:<3} "
            f"{relative} "
            f"(+{added} / -{deleted})"
        )


def print_diff(context: dict) -> None:
    print("=" * 72)
    print("PROJECT DIFF")
    print("=" * 72)
    print(f"リポジトリ   : {context['repository']}")
    print(f"ブランチ     : {context['branch']}")
    print(f"最新コミット : {context['latest_commit']}")

    if context["query"]:
        print(f"絞り込み     : {context['query']}")

    print("-" * 72)

    print_file_group(
        "ステージ済み",
        context["staged"],
        context["staged_numstat"],
    )

    print("-" * 72)

    print_file_group(
        "未ステージ",
        context["unstaged"],
        context["unstaged_numstat"],
    )

    print("-" * 72)
    print("未追跡")

    if context["untracked"]:
        for relative in context["untracked"][:50]:
            print(f"  ??  {relative}")

        omitted = len(context["untracked"]) - 50

        if omitted > 0:
            print(f"  ... ほか {omitted}件")
    else:
        print("  なし")

    print("-" * 72)
    print("差分プレビュー")

    if context["diff_preview"]:
        for line in context["diff_preview"]:
            print(line)
    else:
        print("  差分なし")

    if context["diff_truncated"]:
        print()
        print(
            f"... 差分全{context['diff_total_lines']}行のうち、"
            f"{len(context['diff_preview'])}行を表示"
        )

    print("=" * 72)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Git差分をCodex向けに整理して表示します。"
    )

    parser.add_argument(
        "--repo",
        type=Path,
        default=DEFAULT_REPO,
        help="対象Gitリポジトリ",
    )

    parser.add_argument(
        "--query",
        help="ファイルパスの絞り込み語",
    )

    parser.add_argument(
        "--max-lines",
        type=int,
        default=160,
        help="差分プレビューの最大行数",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = args.repo.expanduser().resolve()

    if not repo.is_dir():
        raise SystemExit(
            f"リポジトリが見つかりません: {repo}"
        )

    code, _, stderr = run_git(
        repo,
        "rev-parse",
        "--show-toplevel",
    )

    if code != 0:
        raise SystemExit(
            f"Gitリポジトリではありません: {stderr or repo}"
        )

    context = collect_diff(
        repo,
        query=args.query,
        max_lines=max(20, args.max_lines),
    )

    print_diff(context)


if __name__ == "__main__":
    main()
