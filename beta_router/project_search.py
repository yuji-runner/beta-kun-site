#!/usr/bin/env python3
"""Fast, bounded, repository-safe text search for Codex."""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

DEFAULT_REPO = Path.home() / "python-study" / "my-dashboard"
DEFAULT_MAX_RESULTS = 50
MAX_FILE_SIZE = 500_000
TEXT_SUFFIXES = {".py", ".html", ".js", ".css", ".json", ".md", ".toml", ".yaml", ".yml", ".txt", ".tsv"}
DEFAULT_EXCLUDES = [".git", "__pycache__", "node_modules", "venv", ".venv", "captures", "logs", "*.bak", ".env", "token.json", "credentials.json", "client_secret.json", "*.pem", "*.key"]
SECRET_NAMES = {".env", "token.json", "credentials.json", "client_secret.json"}


def resolve_paths(repo: Path, paths: list[str] | None) -> list[Path]:
    root = repo.resolve()
    resolved = []
    for raw in paths or ["."]:
        candidate = (root / raw).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"repo外のpathは指定できません: {raw}") from exc
        if not candidate.exists():
            raise ValueError(f"pathが見つかりません: {raw}")
        resolved.append(candidate)
    return resolved


def _relative(repo: Path, path: Path) -> str:
    value = str(path.relative_to(repo.resolve()))
    return value or "."


def _excluded(relative: str, excludes: list[str]) -> bool:
    parts = Path(relative).parts
    return any(
        fnmatch.fnmatch(relative, item) or fnmatch.fnmatch(Path(relative).name, item) or item in parts
        for item in excludes
    )


def _allowed(relative: str, globs: list[str]) -> bool:
    return not globs or any(fnmatch.fnmatch(relative, item) or fnmatch.fnmatch(Path(relative).name, item) for item in globs)


def _walk_files(repo: Path, start: Path, excludes: list[str], include_hidden: bool):
    if start.is_file():
        yield start
        return
    for root, directories, files in os.walk(start, followlinks=False):
        root_path = Path(root)
        kept = []
        for name in directories:
            path = root_path / name
            relative = _relative(repo, path)
            if path.is_symlink() or (not include_hidden and name.startswith(".")) or _excluded(relative, excludes):
                continue
            kept.append(name)
        directories[:] = kept
        for name in files:
            yield root_path / name


def _python_search(repo: Path, query: str, paths: list[Path], globs: list[str], excludes: list[str], max_results: int, fixed_string: bool, case_sensitive: bool, include_hidden: bool) -> tuple[list[dict], bool]:
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(query) if fixed_string else query, flags)
    matches: list[dict] = []
    truncated = False
    for start in paths:
        for path in _walk_files(repo, start, excludes, include_hidden):
            if not path.is_file():
                continue
            relative = _relative(repo, path)
            if (not include_hidden and any(part.startswith(".") for part in Path(relative).parts)) or _excluded(relative, excludes) or not _allowed(relative, globs):
                continue
            if path.name.lower() in SECRET_NAMES or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                if path.stat().st_size > MAX_FILE_SIZE:
                    continue
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for number, line in enumerate(lines, 1):
                if pattern.search(line):
                    if len(matches) >= max_results:
                        return matches, True
                    matches.append({"path": relative, "line": number, "text": line.strip()[:500]})
    return matches, truncated


def _rg_search(repo: Path, query: str, paths: list[Path], globs: list[str], excludes: list[str], max_results: int, fixed_string: bool, case_sensitive: bool, include_hidden: bool) -> tuple[list[dict], bool]:
    command = ["rg", "--json", "--line-number", "--color", "never", "--max-count", str(max_results + 1)]
    if fixed_string:
        command.append("--fixed-strings")
    if case_sensitive:
        command.append("--case-sensitive")
    else:
        command.append("--ignore-case")
    if include_hidden:
        command.append("--hidden")
    for item in globs:
        command.extend(["--glob", item])
    for item in excludes:
        pattern = item if any(char in item for char in "*?[") else f"**/{item}/**"
        command.extend(["--glob", f"!{pattern}"])
    command.extend(["--", query, *[_relative(repo, path) for path in paths]])
    result = subprocess.run(command, cwd=repo, capture_output=True, text=True, timeout=30)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "rg search failed")
    matches = []
    for raw in result.stdout.splitlines():
        event = json.loads(raw)
        if event.get("type") != "match":
            continue
        data = event["data"]
        text = data["lines"]["text"].rstrip("\r\n")[:500]
        for submatch in data.get("submatches") or [{}]:
            relative = data["path"]["text"]
            if relative.startswith("./"):
                relative = relative[2:]
            matches.append({"path": relative, "line": data["line_number"], "text": text})
            break
        if len(matches) > max_results:
            return matches[:max_results], True
    return matches, False


def search_project_report(repo: Path, query: str, *, paths: list[str] | None = None, globs: list[str] | None = None, extensions: list[str] | None = None, excludes: list[str] | None = None, max_results: int = DEFAULT_MAX_RESULTS, fixed_string: bool = False, case_sensitive: bool = False, include_hidden: bool = False, force_python: bool = False) -> dict:
    started = time.perf_counter()
    repo = repo.expanduser().resolve()
    resolved = resolve_paths(repo, paths)
    filters = list(globs or []) + [f"*.{ext.lstrip('.')}" for ext in (extensions or [])]
    excluded = [*DEFAULT_EXCLUDES, *(excludes or [])]
    backend = "python" if force_python or not shutil.which("rg") else "rg"
    search = _python_search if backend == "python" else _rg_search
    results, truncated = search(repo, query, resolved, filters, excluded, max(1, max_results), fixed_string, case_sensitive, include_hidden)
    return {"backend": backend, "query": query, "repo": str(repo), "searched_paths": [_relative(repo, p) for p in resolved], "filters": {"glob": globs or [], "ext": extensions or [], "exclude": excluded, "fixed_string": fixed_string, "case_sensitive": case_sensitive, "include_hidden": include_hidden}, "elapsed_sec": round(time.perf_counter() - started, 4), "result_count": len(results), "truncated": truncated, "results": results}


def search_project(repo: Path, query: str, *, limit: int = 30, **kwargs) -> list[dict]:
    """Backward-compatible file-grouped result used by v1 callers."""
    report = search_project_report(repo, query, max_results=limit, **kwargs)
    grouped: dict[str, dict] = {}
    for match in report["results"]:
        item = grouped.setdefault(match["path"], {"path": match["path"], "score": 0, "matches": []})
        item["score"] += 3
        item["matches"].append({"line": match["line"], "text": match["text"]})
    return list(grouped.values())


def print_search(report: dict) -> None:
    print("=" * 72); print(f"PROJECT SEARCH: {report['query']}"); print("=" * 72)
    print(f"backend: {report['backend']}"); print(f"repo: {report['repo']}"); print(f"searched paths: {', '.join(report['searched_paths'])}")
    print(f"filters: {json.dumps(report['filters'], ensure_ascii=False)}"); print(f"elapsed_sec: {report['elapsed_sec']:.4f}")
    print(f"result_count: {report['result_count']}"); print(f"truncated: {str(report['truncated']).lower()}"); print("-" * 72)
    for item in report["results"]:
        print(f"{item['path']}:{item['line']}:{item['text']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="プロジェクト内を高速検索します。")
    parser.add_argument("query"); parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--path", action="append", dest="paths"); parser.add_argument("--glob", action="append", dest="globs")
    parser.add_argument("--ext", action="append", dest="extensions"); parser.add_argument("--exclude", action="append", dest="excludes")
    parser.add_argument("--max-results", "--limit", type=int, default=DEFAULT_MAX_RESULTS)
    parser.add_argument("--fixed-string", action="store_true"); parser.add_argument("--case-sensitive", action="store_true"); parser.add_argument("--include-hidden", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        print_search(search_project_report(args.repo, args.query, paths=args.paths, globs=args.globs, extensions=args.extensions, excludes=args.excludes, max_results=args.max_results, fixed_string=args.fixed_string, case_sensitive=args.case_sensitive, include_hidden=args.include_hidden))
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(f"エラー: {exc}")


if __name__ == "__main__":
    main()
