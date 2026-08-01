#!/usr/bin/env python3
"""Contract tests for βRouter v1.2 local inspection tools."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

if __package__:
    from . import project_diff, project_search, task_metrics
    from .codex_tools import run_finish
else:
    import project_diff, project_search, task_metrics
    from codex_tools import run_finish


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.repo = Path(self.temp.name)
        (self.repo / "src").mkdir(); (self.repo / "data").mkdir(); (self.repo / ".hidden").mkdir()
        (self.repo / "src" / "a.py").write_text("COLCHICINE\nコルヒチン\nneedle.literal\n", encoding="utf-8")
        (self.repo / "src" / "b.json").write_text('{"drug":"コルヒチン"}\n', encoding="utf-8")
        (self.repo / "data" / "c.tsv").write_text("name\tコルヒチン\n", encoding="utf-8")
        (self.repo / ".hidden" / "x.py").write_text("コルヒチン\n", encoding="utf-8")
        (self.repo / "skip.bak").write_text("コルヒチン\n", encoding="utf-8")
    def tearDown(self): self.temp.cleanup()
    def search(self, **kwargs): return project_search.search_project_report(self.repo, "コルヒチン", **kwargs)
    def test_rg_backend_and_japanese(self): self.assertEqual("rg", self.search()["backend"]); self.assertTrue(self.search()["results"])
    def test_python_fallback(self):
        with patch.object(project_search.shutil, "which", return_value=None):
            self.assertEqual("python", self.search()["backend"])
    def test_file_directory_and_multiple_paths(self):
        self.assertEqual(1, self.search(paths=["src/a.py"])["result_count"])
        self.assertTrue(self.search(paths=["src"])["results"])
        self.assertEqual(2, self.search(paths=["src/a.py", "data/c.tsv"])["result_count"])
    def test_ext_single_multiple_json_tsv(self):
        self.assertTrue(all(x["path"].endswith(".py") for x in self.search(extensions=["py"])["results"]))
        self.assertEqual({".py", ".json"}, {Path(x["path"]).suffix for x in self.search(extensions=["py", "json"])["results"]})
        self.assertEqual("data/c.tsv", self.search(extensions=["tsv"])["results"][0]["path"])
    def test_glob_exclude(self):
        self.assertTrue(all(x["path"].endswith(".json") for x in self.search(globs=["*.json"])["results"]))
        self.assertFalse(any(x["path"].startswith("src/") for x in self.search(excludes=["src"])["results"]))
    def test_max_results_and_truncated(self):
        report = self.search(max_results=1); self.assertEqual(1, report["result_count"]); self.assertTrue(report["truncated"])
    def test_case_fixed_string(self):
        sensitive = project_search.search_project_report(self.repo, "colchicine", case_sensitive=True)
        self.assertFalse(sensitive["results"])
        fixed = project_search.search_project_report(self.repo, "needle.literal", fixed_string=True)
        self.assertEqual(1, fixed["result_count"])
    def test_outside_and_symlink_escape(self):
        with self.assertRaises(ValueError): self.search(paths=["../outside"])
        outside = Path(self.temp.name).parent / "outside-search"; outside.mkdir(exist_ok=True)
        link = self.repo / "escape"; link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError): self.search(paths=["escape"])
    def test_hidden_policy(self):
        self.assertFalse(any(".hidden" in x["path"] for x in self.search()["results"]))
        self.assertTrue(any(".hidden" in x["path"] for x in self.search(include_hidden=True)["results"]))


class DiffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.repo, check=True)
        (self.repo / ".gitignore").write_text("*.json\n.env\n", encoding="utf-8")
        (self.repo / "a.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore", "a.txt"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=self.repo, check=True)
        (self.repo / "a.txt").write_text("base\nunstaged 日本語\n", encoding="utf-8")
        (self.repo / "staged.txt").write_text("staged\n", encoding="utf-8"); subprocess.run(["git", "add", "staged.txt"], cwd=self.repo, check=True)
        (self.repo / "new.txt").write_text("untracked 日本語\n", encoding="utf-8")
        (self.repo / "artifact.json").write_text('{"ok":true}\n', encoding="utf-8")
        (self.repo / "token.json").write_text('{"token":"secret"}\n', encoding="utf-8")
    def tearDown(self): self.temp.cleanup()
    def test_classification_and_modes(self):
        all_items = project_diff.collect_diff(self.repo)
        self.assertEqual((1, 1, 1), (all_items["counts"]["staged"], all_items["counts"]["unstaged"], all_items["counts"]["untracked"]))
        self.assertEqual(1, project_diff.collect_diff(self.repo, staged=True)["counts"]["staged"])
        self.assertEqual(0, project_diff.collect_diff(self.repo, staged=True)["counts"]["untracked"])
        self.assertEqual(1, project_diff.collect_diff(self.repo, unstaged=True)["counts"]["unstaged"])
        self.assertTrue(project_diff.collect_diff(self.repo, untracked=True)["previews"]["untracked"])
    def test_path_multiple_empty_and_japanese_content(self):
        self.assertEqual(1, project_diff.collect_diff(self.repo, paths=["a.txt"])["counts"]["unstaged"])
        self.assertEqual(2, sum(project_diff.collect_diff(self.repo, paths=["a.txt", "new.txt"])["counts"].values()))
        self.assertEqual(0, sum(project_diff.collect_diff(self.repo, paths=[".gitignore"])["counts"].values()))
        preview = project_diff.collect_diff(self.repo, paths=["new.txt"], untracked=True)["previews"]["untracked"][0]
        self.assertIn("日本語", "".join(preview["content"]))
    def test_untracked_binary_large_and_limits(self):
        (self.repo / "binary.bin").write_bytes(b"x\0y"); (self.repo / "large.txt").write_bytes(b"x" * (project_diff.MAX_CONTENT_SIZE + 1))
        binary = project_diff.collect_diff(self.repo, paths=["binary.bin"], untracked=True)["previews"]["untracked"][0]
        large = project_diff.collect_diff(self.repo, paths=["large.txt"], untracked=True)["previews"]["untracked"][0]
        self.assertIn("binary", binary["reason"]); self.assertIn("large", large["reason"])
        self.assertTrue(project_diff.collect_diff(self.repo, untracked=True, max_files=1)["truncated"])
        self.assertTrue(project_diff.collect_diff(self.repo, untracked=True, max_lines=1)["truncated"])
    def test_ignored_explicit_and_secret(self):
        hidden = project_diff.collect_diff(self.repo, paths=["artifact.json"])
        self.assertEqual(0, hidden["counts"]["ignored"])
        shown = project_diff.collect_diff(self.repo, paths=["artifact.json"], include_ignored=True)
        self.assertEqual(1, shown["counts"]["ignored"]); self.assertTrue(shown["previews"]["ignored"][0]["content"])
        secret = project_diff.collect_diff(self.repo, paths=["token.json"], include_ignored=True)["previews"]["ignored"][0]
        self.assertIn("secret-like", secret["reason"]); self.assertFalse(secret["content"])
    def test_summary_only_and_escapes(self):
        self.assertFalse(any(project_diff.collect_diff(self.repo, summary_only=True)["previews"].values()))
        with self.assertRaises(ValueError): project_diff.collect_diff(self.repo, paths=["../outside"])
        outside = Path(self.temp.name).parent / "outside-diff"; outside.mkdir(exist_ok=True)
        (self.repo / "escape").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError): project_diff.collect_diff(self.repo, paths=["escape"])
    def test_submodule_pointer_metadata_contract(self):
        responses = [
            (0, "160000 abcdef 0\tbeta-kun-site", ""),
            (0, "-Subproject commit 111111\n+Subproject commit 222222-dirty", ""),
        ]
        with patch.object(project_diff, "run_git", side_effect=responses):
            result = project_diff._submodules(self.repo, [{"status": "M", "path": "beta-kun-site"}])
        self.assertEqual("beta-kun-site", result[0]["path"])
        self.assertEqual("111111", result[0]["old_sha"])
        self.assertIn("--repo", result[0]["command"])


class FinishTests(unittest.TestCase):
    def test_finish_summary_duplicate_and_write_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "metrics.jsonl"
            with patch.object(task_metrics, "METRICS_FILE", log):
                first = task_metrics.TaskMetrics(repo=Path(directory), command="codex_tools.py", subcommand="search", task_id="same")
                first.finish("success")
                summary = task_metrics.summarize_task("same")
                self.assertEqual(2, summary["command_count"]); self.assertEqual(1, summary["search_count"]); self.assertFalse(summary["duplicate_finish"])
                finish = task_metrics.TaskMetrics(repo=Path(directory), command="codex_tools.py", subcommand="finish", task_id="same", additional_instruction_count=2, rework_count=1)
                finish.extra_fields.update(summary); finish.finish("success")
                record = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
                self.assertEqual((2, 1), (record["additional_instruction_count"], record["rework_count"])); self.assertEqual(0, record["logical_provider_calls"])
                self.assertTrue(task_metrics.summarize_task("same")["duplicate_finish"])
            with patch.object(task_metrics, "METRICS_FILE", Path("/proc/no/task.jsonl")):
                task_metrics.TaskMetrics(repo=None, command="codex_tools.py", subcommand="finish").finish("success")
    def test_task_id_default_is_preserved(self):
        self.assertTrue(task_metrics.TaskMetrics(repo=None, command="x").task_id)


if __name__ == "__main__": unittest.main()
