#!/usr/bin/env python3
"""Codex向けの軽量プロジェクト検索。"""

import argparse
import re
from pathlib import Path


DEFAULT_REPO = Path.home() / "python-study" / "my-dashboard"

TEXT_SUFFIXES = {
    ".py",
    ".html",
    ".js",
    ".css",
    ".json",
    ".md",
    ".toml",
    ".yaml",
    ".yml",
    ".txt",
    ".tsv",
}

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

EXCLUDED_NAMES = {
    "project_context.json",
    "codex_prompt.txt",
}

MAX_FILE_SIZE = 500_000
MAX_MATCHES_PER_FILE = 5


def is_safe_file(path: Path, repo: Path) -> bool:
    try:
        relative = path.resolve().relative_to(repo.resolve())
    except (ValueError, OSError):
        return False

    if path.name in SECRET_NAMES:
        return False

    if path.name in EXCLUDED_NAMES:
        return False

    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False

    if any(
        part.startswith(EXCLUDED_PREFIXES)
        for part in relative.parts
    ):
        return False

    if path.suffix.lower() not in TEXT_SUFFIXES:
        return False

    try:
        return (
            path.is_file()
            and path.stat().st_size <= MAX_FILE_SIZE
        )
    except OSError:
        return False


def search_project(
    repo: Path,
    query: str,
    *,
    limit: int = 30,
) -> list[dict]:
    pattern = re.compile(
        re.escape(query),
        flags=re.IGNORECASE,
    )

    results = []

    for path in repo.rglob("*"):
        if not is_safe_file(path, repo):
            continue

        relative = str(path.relative_to(repo))
        score = 0
        matches = []

        if pattern.search(relative):
            score += 20

        try:
            lines = path.read_text(
                encoding="utf-8",
                errors="replace",
            ).splitlines()
        except OSError:
            continue

        for line_number, line in enumerate(lines, start=1):
            if not pattern.search(line):
                continue

            score += 3

            if len(matches) < MAX_MATCHES_PER_FILE:
                matches.append({
                    "line": line_number,
                    "text": line.strip()[:240],
                })

        if score == 0:
            continue

        results.append({
            "path": relative,
            "score": score,
            "matches": matches,
        })

    results.sort(
        key=lambda item: (
            -item["score"],
            len(item["path"]),
            item["path"],
        )
    )

    return results[:limit]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="プロジェクト内の関連ファイルを検索します。"
    )

    parser.add_argument(
        "query",
        help="検索語",
    )

    parser.add_argument(
        "--repo",
        type=Path,
        default=DEFAULT_REPO,
        help="検索対象ディレクトリ",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="最大表示件数",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = args.repo.expanduser().resolve()

    if not repo.is_dir():
        raise SystemExit(
            f"検索対象が見つかりません: {repo}"
        )

    results = search_project(
        repo,
        args.query,
        limit=args.limit,
    )

    print("=" * 64)
    print(f"PROJECT SEARCH: {args.query}")
    print(f"対象: {repo}")
    print("=" * 64)

    if not results:
        print("該当ファイルは見つかりませんでした。")
        return

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


if __name__ == "__main__":
    main()
