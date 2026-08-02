#!/usr/bin/env python3
"""Bounded and classified Git diff inspection for Codex."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

DEFAULT_REPO = Path.home() / "python-study" / "my-dashboard"
DEFAULT_MAX_FILES = 50
DEFAULT_MAX_LINES = 500
MAX_CONTENT_SIZE = 500_000
SECRET_WORDS = (".env", "token", "secret", "credential", "private", "api_key", "api-key", "apikey", "id_rsa", "id_ed25519", ".key", ".pem")
EXCLUDED_PARTS = {".git", "__pycache__", "node_modules", "venv", ".venv"}


def run_git(repo: Path, *args: str) -> tuple[int, str, str]:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout.rstrip(), result.stderr.rstrip()


def bounded_git_lines(repo: Path, args: list[str], limit: int) -> tuple[list[str], bool]:
    """Stream at most limit lines so a huge diff is never fully buffered."""
    process = subprocess.Popen(["git", *args], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lines = []
    assert process.stdout is not None
    truncated = False
    try:
        for line in process.stdout:
            if len(lines) >= limit:
                process.terminate()
                truncated = True
                break
            lines.append(line.rstrip("\n"))
    finally:
        if process.poll() is None:
            process.wait(timeout=5)
    error = process.stderr.read().strip() if process.stderr else ""
    process.stdout.close()
    if process.stderr:
        process.stderr.close()
    if truncated:
        return lines, True
    if process.returncode not in (0, -15):
        raise RuntimeError(error or "git diff failed")
    return lines, False


def resolve_paths(repo: Path, paths: list[str] | None, *, require_exists: bool = True) -> list[str]:
    root = repo.resolve()
    result = []
    for raw in paths or []:
        candidate = (root / raw).resolve()
        try:
            relative = candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"repo外のpathは指定できません: {raw}") from exc
        if require_exists and not candidate.exists():
            raise ValueError(f"pathが見つかりません: {raw}")
        result.append(str(relative))
    return result


def is_safe_relative_path(relative: str) -> bool:
    path = Path(relative)
    return not any(part in EXCLUDED_PARTS for part in path.parts) and not path.name.endswith((".pyc", ".pid", ".bak", "~"))


def is_secret_path(relative: str) -> bool:
    lowered = relative.lower()
    return any(word in lowered for word in SECRET_WORDS)


def _path_selected(relative: str, paths: list[str]) -> bool:
    return not paths or any(relative == item or relative.startswith(item.rstrip("/") + "/") for item in paths)


def _name_status(repo: Path, cached: bool, paths: list[str]) -> list[dict]:
    args = ["diff", "--name-status"] + (["--cached"] if cached else [])
    if paths:
        args.extend(["--", *paths])
    code, output, error = run_git(repo, *args)
    if code:
        raise RuntimeError(error or "git diff failed")
    items = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and is_safe_relative_path(parts[-1]):
            items.append({"status": parts[0], "path": parts[-1]})
    return items


def _list_files(repo: Path, ignored: bool, paths: list[str]) -> list[str]:
    args = ["ls-files", "--others", "--exclude-standard"]
    if ignored:
        args = ["ls-files", "--others", "--ignored", "--exclude-standard"]
    if paths:
        args.extend(["--", *paths])
    code, output, _ = run_git(repo, *args)
    if code:
        return []
    return [item for item in output.splitlines() if is_safe_relative_path(item) and _path_selected(item, paths)]


def _file_preview(repo: Path, relative: str, max_lines: int) -> dict:
    path = repo / relative
    result = {"path": relative, "content": [], "reason": None, "truncated": False}
    if is_secret_path(relative):
        result["reason"] = "secret-like path; content hidden"; return result
    try:
        size = path.stat().st_size
        if size > MAX_CONTENT_SIZE:
            result["reason"] = f"large file ({size} bytes); summary only"; return result
        raw = path.read_bytes()
    except OSError as exc:
        result["reason"] = f"unreadable: {exc}"; return result
    if b"\0" in raw:
        result["reason"] = "binary file; content hidden"; return result
    lines = raw.decode("utf-8", errors="replace").splitlines()
    result["content"] = [f"+{line}" for line in lines[:max_lines]]
    result["truncated"] = len(lines) > max_lines
    return result


def _submodules(repo: Path, items: list[dict]) -> list[dict]:
    result = []
    for item in items:
        code, entry, _ = run_git(repo, "ls-files", "-s", "--", item["path"])
        if code or not entry.startswith("160000 "):
            continue
        _, text, _ = run_git(repo, "diff", "--submodule=short", "--", item["path"])
        old = new = None
        for line in text.splitlines():
            if line.startswith("-Subproject commit "): old = line.rsplit(" ", 1)[-1].rstrip("-dirty")
            if line.startswith("+Subproject commit "): new = line.rsplit(" ", 1)[-1].rstrip("-dirty")
        result.append({"path": item["path"], "old_sha": old, "new_sha": new, "command": f"python3 {item['path']}/beta_router/codex_tools.py --repo {repo / item['path']} diff"})
    return result


def collect_diff(repo: Path, *, query: str | None = None, paths: list[str] | None = None, staged: bool = False, unstaged: bool = False, untracked: bool = False, include_ignored: bool = False, summary_only: bool = False, max_files: int = DEFAULT_MAX_FILES, max_lines: int = DEFAULT_MAX_LINES) -> dict:
    repo = repo.expanduser().resolve()
    selected_paths = resolve_paths(repo, paths)
    explicit_tracked_modes = staged or unstaged
    show_staged = staged if explicit_tracked_modes else True
    show_unstaged = unstaged if explicit_tracked_modes else True
    staged_items = _name_status(repo, True, selected_paths) if show_staged else []
    unstaged_items = _name_status(repo, False, selected_paths) if show_unstaged else []
    show_untracked = untracked or not explicit_tracked_modes
    untracked_files = _list_files(repo, False, selected_paths) if show_untracked else []
    if query:
        accept = lambda value: query.lower() in value.lower()
        staged_items = [x for x in staged_items if accept(x["path"])]
        unstaged_items = [x for x in unstaged_items if accept(x["path"])]
        untracked_files = [x for x in untracked_files if accept(x)]
    ignored_status = "collected" if include_ignored and selected_paths else ("skipped" if include_ignored else "not_requested")
    ignored_reason = "explicit path required" if ignored_status == "skipped" else None
    ignored_files = _list_files(repo, True, selected_paths) if ignored_status == "collected" else []
    requested = {
        "staged": show_staged,
        "unstaged": show_unstaged,
        "untracked": show_untracked,
        "ignored": include_ignored,
    }
    statuses = {
        "staged": "collected" if show_staged else "not_requested",
        "unstaged": "collected" if show_unstaged else "not_requested",
        "untracked": "collected" if show_untracked else "not_requested",
        "ignored": ignored_status,
    }
    total_counts = {
        "staged": len(staged_items) if show_staged else None,
        "unstaged": len(unstaged_items) if show_unstaged else None,
        "untracked": len(untracked_files) if show_untracked else None,
        "ignored": len(ignored_files) if ignored_status == "collected" else None,
    }
    all_files = [x["path"] for x in staged_items + unstaged_items] + untracked_files + ignored_files
    truncated_files = len(dict.fromkeys(all_files)) > max_files
    permitted = set(list(dict.fromkeys(all_files))[:max_files])
    staged_items = [x for x in staged_items if x["path"] in permitted]
    unstaged_items = [x for x in unstaged_items if x["path"] in permitted]
    untracked_files = [x for x in untracked_files if x in permitted]
    ignored_files = [x for x in ignored_files if x in permitted]
    previews = {"staged": [], "unstaged": [], "untracked": [], "ignored": []}
    lines_left = max_lines
    truncated_lines = False
    if not summary_only:
        for key, cached, items in (("staged", True, staged_items), ("unstaged", False, unstaged_items)):
            if not items or lines_left <= 0: continue
            args = ["diff", "--no-ext-diff", "--unified=2"] + (["--cached"] if cached else []) + ["--", *[x["path"] for x in items]]
            lines, cut = bounded_git_lines(repo, args, lines_left)
            previews[key] = lines; lines_left -= len(lines); truncated_lines = truncated_lines or cut
        if untracked:
            for relative in untracked_files:
                if lines_left <= 0: break
                preview = _file_preview(repo, relative, lines_left); previews["untracked"].append(preview); lines_left -= len(preview["content"])
        for relative in ignored_files:
            if lines_left <= 0: break
            preview = _file_preview(repo, relative, lines_left); previews["ignored"].append(preview); lines_left -= len(preview["content"])
    _, branch, _ = run_git(repo, "branch", "--show-current")
    _, latest, _ = run_git(repo, "log", "-1", "--oneline")
    sections = {
        key: {
            "requested": requested[key],
            "status": statuses[key],
            "count": total_counts[key],
            "reason": ignored_reason if key == "ignored" else None,
        }
        for key in ("staged", "unstaged", "untracked", "ignored")
    }
    return {"repository": str(repo), "branch": branch or "(detached)", "latest_commit": latest, "query": query, "paths": selected_paths, "staged": staged_items, "unstaged": unstaged_items, "untracked": untracked_files, "ignored": ignored_files, "sections": sections, "previews": previews, "counts": total_counts, "displayed_counts": {"staged": len(staged_items), "unstaged": len(unstaged_items), "untracked": len(untracked_files), "ignored": len(ignored_files)}, "truncated": truncated_files or truncated_lines or lines_left <= 0, "max_files": max_files, "max_lines": max_lines, "submodules": _submodules(repo, staged_items + unstaged_items)}


def print_diff(context: dict) -> None:
    print("=" * 72); print("PROJECT DIFF"); print("=" * 72)
    print(f"repository: {context['repository']}"); print(f"branch: {context['branch']}"); print(f"latest_commit: {context['latest_commit']}"); print(f"paths: {context['paths'] or ['.']}")
    for key, title in (("staged", "staged"), ("unstaged", "unstaged"), ("untracked", "untracked"), ("ignored", "ignored relevant files")):
        section = context["sections"][key]
        print("-" * 72)
        if section["status"] == "not_requested":
            print(f"{title}: not requested")
            continue
        if section["status"] == "skipped":
            print(f"{title}: skipped")
            print(f"  reason: {section['reason']}")
            continue
        print(f"{title} ({section['count']})")
        items = context[key]
        for item in items:
            print(f"  {item.get('status', '??') if isinstance(item, dict) else '??'}  {item['path'] if isinstance(item, dict) else item}")
        if not items: print("  none")
        preview = context["previews"][key]
        if preview and isinstance(preview[0], str):
            print(*preview, sep="\n")
        else:
            for entry in preview:
                print(f"--- /dev/null\n+++ {entry['path']}")
                if entry["reason"]: print(f"[summary only] {entry['reason']}")
                else: print(*entry["content"], sep="\n")
                if entry["truncated"]: print("[content truncated]")
    for submodule in context["submodules"]:
        print(f"submodule: {submodule['path']} old={submodule['old_sha']} new={submodule['new_sha']}"); print(f"  internal diff: {submodule['command']}")
    print(f"truncated: {str(context['truncated']).lower()}")
    if context["truncated"]: print("続き: --path <対象> --max-files <件数> --max-lines <行数> で限定してください")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Git差分を安全に分類表示します。")
    p.add_argument("--repo", type=Path, default=DEFAULT_REPO); p.add_argument("--query")
    p.add_argument("--path", action="append", dest="paths"); p.add_argument("--staged", action="store_true"); p.add_argument("--unstaged", action="store_true"); p.add_argument("--untracked", action="store_true")
    p.add_argument("--include-ignored", action="store_true"); p.add_argument("--summary-only", action="store_true"); p.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES); p.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    return p.parse_args()


def main() -> None:
    a = parse_args()
    try: print_diff(collect_diff(a.repo, query=a.query, paths=a.paths, staged=a.staged, unstaged=a.unstaged, untracked=a.untracked, include_ignored=a.include_ignored, summary_only=a.summary_only, max_files=max(1, a.max_files), max_lines=max(1, a.max_lines)))
    except (ValueError, RuntimeError) as exc: raise SystemExit(f"エラー: {exc}")


if __name__ == "__main__": main()
