#!/usr/bin/env python3
"""NVIDIA NIMでCodex向け実行指示を事前作成する。"""

import argparse
import subprocess
from pathlib import Path

try:
    from .providers.nvidia import NvidiaProvider
    from .task_metrics import TaskMetrics
except ImportError:
    from providers.nvidia import NvidiaProvider
    from task_metrics import TaskMetrics


DEFAULT_REPO = Path.home() / "python-study" / "my-dashboard"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "codex_prompt.txt"

MAX_FILE_COUNT = 8
MAX_FILE_CHARS = 12_000
MAX_TOTAL_CHARS = 48_000

EXCLUDED_NAMES = {
    ".env",
    "token.json",
    "credentials.json",
    "client_secret.json",
}

EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "logs",
    "captures",
}


def run_command(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"コマンド失敗: {' '.join(args)}\n"
            f"{result.stderr.strip()}"
        )

    return result.stdout.strip()


def is_safe_path(path: Path, repo: Path) -> bool:
    try:
        relative = path.resolve().relative_to(repo.resolve())
    except ValueError:
        return False

    if path.name in EXCLUDED_NAMES:
        return False

    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False

    return path.is_file()


def list_tracked_files(repo: Path) -> list[str]:
    """
    Git追跡済みファイルと未追跡ファイルを取得する。

    .gitignore対象は除外する。
    -zを使い、空白・日本語・引用符・改行を含むファイル名も
    Gitの表示用エスケープを通さず安全に取得する。
    """
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        cwd=repo,
        capture_output=True,
        timeout=30,
    )

    if result.returncode != 0:
        stderr = result.stderr.decode(
            "utf-8",
            errors="replace",
        ).strip()

        raise RuntimeError(
            "git ls-filesに失敗しました。\n"
            f"{stderr}"
        )

    files: list[str] = []

    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue

        relative = raw_path.decode(
            "utf-8",
            errors="surrogateescape",
        )

        candidate_path = repo / relative

        try:
            safe = is_safe_path(candidate_path, repo)
        except OSError as error:
            print(
                f"警告: ファイル確認を省略しました: "
                f"{relative} ({error})",
                flush=True,
            )
            continue

        if safe:
            files.append(relative)

    return files


def get_git_status(repo: Path) -> str:
    return run_command(
        ["git", "status", "--short"],
        cwd=repo,
    ) or "変更なし"


def extract_search_terms(task: str) -> list[str]:
    """依頼文からファイル検索に使う語を抽出する。"""
    normalized = task.lower()

    aliases = {
        "βrouter": [
            "beta_router",
            "router",
        ],
        "nvidia": [
            "nvidia",
            "nim",
        ],
        "provider": [
            "provider",
            "providers",
        ],
        "flask": [
            "flask",
            "app.py",
        ],
        "codex": [
            "codex",
        ],
        "ログ": [
            "log",
            "logger",
            "summary",
        ],
        "api": [
            "api",
        ],
        "テスト": [
            "test",
            "tests",
        ],
    }

    terms: list[str] = []

    for source, expanded in aliases.items():
        if source in normalized:
            terms.extend(expanded)

    for token in normalized.replace("。", " ").replace("、", " ").split():
        token = token.strip(
            ".,:;()[]{}<>「」『』"
        )

        if len(token) >= 3:
            terms.append(token)

    # 順序を保ったまま重複除去
    return list(dict.fromkeys(terms))


def select_candidate_files(
    repo: Path,
    task: str,
    files: list[str],
) -> list[str]:
    """
    ファイル名とコード本文をローカルで採点し、
    NVIDIAへ送る候補を絞る。
    """
    terms = extract_search_terms(task)
    scored: list[tuple[int, str]] = []

    preferred_extensions = {
        ".py",
        ".html",
        ".js",
        ".css",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".md",
    }

    for relative in files:
        candidate = repo / relative
        suffix = candidate.suffix.lower()

        if suffix not in preferred_extensions:
            continue

        relative_lower = relative.lower()
        score = 0

        for term in terms:
            term_lower = term.lower()

            if term_lower in relative_lower:
                score += 12

        # βRouter関連の依頼では、専用ディレクトリを強く優先する。
        if "βrouter" in task.lower() or "beta_router" in task.lower():
            if relative_lower.startswith("beta_router/"):
                score += 40

        if "nvidia" in task.lower():
            if "nvidia" in relative_lower:
                score += 50

        if "provider" in task.lower():
            if "/providers/" in relative_lower:
                score += 25

        if "beta_router" in relative_lower:
            score += 12

        if relative_lower.endswith(
            (
                "router.py",
                "config.py",
                "app.py",
            )
        ):
            score += 4

        # ファイル名だけで候補にならない場合も、
        # 小さめのテキストファイルは本文を確認する。
        try:
            if candidate.stat().st_size <= 300_000:
                content = candidate.read_text(
                    encoding="utf-8",
                    errors="replace",
                )[:100_000].lower()

                for term in terms:
                    if term.lower() in content:
                        score += 3
        except OSError:
            continue

        if score > 0:
            scored.append((score, relative))

    scored.sort(
        key=lambda item: (
            -item[0],
            len(item[1]),
            item[1],
        )
    )

    return [
        relative
        for _, relative in scored[:MAX_FILE_COUNT]
    ]


def read_candidate_files(
    repo: Path,
    candidates: list[str],
) -> str:
    sections = []
    total_chars = 0

    for relative in candidates:
        path = repo / relative

        if not is_safe_path(path, repo):
            continue

        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            continue

        text = text[:MAX_FILE_CHARS]

        remaining = MAX_TOTAL_CHARS - total_chars
        if remaining <= 0:
            break

        text = text[:remaining]
        total_chars += len(text)

        sections.append(
            f"===== FILE: {relative} =====\n{text}"
        )

    return "\n\n".join(sections)


def build_codex_prompt(
    provider: NvidiaProvider,
    *,
    task: str,
    repo: Path,
    git_status: str,
    candidates: list[str],
    source_context: str,
) -> str:
    candidate_text = "\n".join(
        f"- {path}" for path in candidates
    ) or "- 候補なし"

    prompt = f"""
あなたはCodexの作業時間を短縮する前処理担当です。
以下の実コードと依頼に基づき、Codex CLIへ渡す実行指示を作成してください。

【リポジトリ】
{repo}

【依頼】
{task}

【現在のgit status】
{git_status}

【関連ファイル候補】
{candidate_text}

【実コード】
{source_context or "関連コードを取得できませんでした。"}

【重要事項】
- 実コードから確認できないファイル、API、関数を創作しない
- 既存の未コミット変更を消さない
- APIキー、.env、認証情報を表示・編集・コミットしない
- 必要最小限の変更にする
- 既存仕様との互換性を保つ
- 編集後に構文確認と関連テストを実行する
- テストできない場合は理由を明示する
- 最後に変更ファイル、テスト結果、残課題を報告させる

【実行要否の判定】
回答の1行目には、必ず次のどちらかだけを書いてください。

CODEX_ACTION: RUN
CODEX_ACTION: SKIP

次の場合は必ずSKIPにしてください。
- 実コードを確認した結果、依頼された機能が既に実装済み
- 「確認し、必要なら改善」の依頼で、具体的な欠陥を特定できない
- 現在の実装が合理的で、変更候補が任意改善にすぎない
- 調査・説明・確認だけで目的を達成できる
- Codexを起動しても必要な実ファイル編集が発生しない
- リトライ回数、待機時間、ログ表現などを好みで変えるだけの場合

次の場合だけRUNにしてください。
- 実コード上の具体的な欠陥を、ファイル名・該当処理・理由とともに特定できた
- 依頼された機能が未実装または明確に不完全
- バグ修正、必須仕様への適合、必要なテスト追加など、実編集が不可欠
- Codexによるコマンド実行が目的達成に必須

RUNと判定する場合は、回答中に必ず
「具体的な欠陥」
という見出しを設け、実コードに基づく欠陥を明記してください。
具体的な欠陥を書けない場合はSKIPにしてください。
任意の改善案だけを理由にRUNとしてはいけません。

【出力形式】
1行目の判定に続けて、根拠のある結果を出力してください。
挨拶や不要な前置きは付けないでください。

RUNの場合は、Codexにそのまま渡せる命令文として次を明記してください。

1. 目的
2. 事前確認
3. 変更対象
4. 実装方針
5. 禁止事項
6. テスト
7. 完了条件

SKIPの場合は、次を簡潔に記載してください。

1. Codexを起動しない理由
2. 実コードで確認できた内容
3. 残課題
""".strip()

    return provider.chat(prompt).strip()


def parse_codex_action(result: str) -> tuple[str, str]:
    """NVIDIAの回答からCodex実行要否と本文を取り出す。"""
    lines = result.strip().splitlines()

    if not lines:
        raise RuntimeError(
            "NVIDIAから空のCodex判定が返りました。"
        )

    first_line = lines[0].strip().upper()

    if first_line == "CODEX_ACTION: RUN":
        action = "run"
    elif first_line == "CODEX_ACTION: SKIP":
        action = "skip"
    else:
        raise RuntimeError(
            "NVIDIAの回答にCODEX_ACTION判定がありません。"
        )

    body = "\n".join(lines[1:]).strip()

    return action, body


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NVIDIA NIMでCodex向け指示を作成します。"
    )

    parser.add_argument(
        "task",
        help="実施したい開発依頼",
    )

    parser.add_argument(
        "--repo",
        type=Path,
        default=DEFAULT_REPO,
        help="対象Gitリポジトリ",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Codex指示の保存先",
    )

    parser.add_argument("--task-id", help="既存の計測task_idを引き継ぐ")
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

    return parser.parse_args()


def run_prepare(args: argparse.Namespace, metrics: TaskMetrics) -> None:
    repo = args.repo.expanduser().resolve()
    output = args.output.expanduser().resolve()

    if not repo.is_dir():
        raise SystemExit(
            f"リポジトリが見つかりません: {repo}"
        )

    if not (repo / ".git").exists():
        raise SystemExit(
            f"Gitリポジトリではありません: {repo}"
        )

    provider = NvidiaProvider()

    print("1/4 追跡ファイルを取得しています...")
    files = list_tracked_files(repo)

    print(f"    対象ファイル数: {len(files)}")

    print("2/4 ローカルで関連ファイルを選定しています...")
    candidates = select_candidate_files(
        repo,
        args.task,
        files,
    )

    print("    関連ファイル候補:")
    if candidates:
        for candidate in candidates:
            print(f"    - {candidate}")
    else:
        print("    - 候補を取得できませんでした")

    print("3/4 関連コードを収集しています...")
    source_context = read_candidate_files(
        repo,
        candidates,
    )

    print("4/4 Codex向け指示を作成しています...")
    metrics.provider_call("nvidia", "codex_prompt_generation")
    nvidia_result = build_codex_prompt(
        provider,
        task=args.task,
        repo=repo,
        git_status=get_git_status(repo),
        candidates=candidates,
        source_context=source_context,
    )

    action, codex_prompt = parse_codex_action(
        nvidia_result
    )
    metrics.prompt_generated = True

    print()
    print("=" * 60)

    if action == "skip":
        print("判定: Codex起動不要")
        print()
        print(codex_prompt)
        print("=" * 60)
        print()
        print(
            "NVIDIAの事前確認で目的を達成したため、"
            "Codexは起動しません。"
        )

        if output.exists():
            output.unlink()
            print(f"古いCodex指示を削除しました: {output}")

        return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        codex_prompt + "\n",
        encoding="utf-8",
    )

    print("判定: Codex起動が必要")
    print()
    print(codex_prompt)
    print("=" * 60)
    print()
    print(f"保存先: {output}")
    print()
    print("内容を確認後、次でCodexを実行できます:")
    print(
        f'codex exec -C "{repo}" '
        f'--sandbox workspace-write - < "{output}"'
    )


def main() -> None:
    args = parse_args()
    repo = args.repo.expanduser().resolve()
    metrics = TaskMetrics(
        repo=repo,
        command="codex_prepare.py",
        subcommand="prepare",
        task_description=args.task,
        task_id=args.task_id,
        provider="nvidia",
        provider_purpose="codex_prompt_generation",
        additional_instruction_count=args.additional_instructions,
        rework_count=args.rework_count,
    )

    with metrics:
        run_prepare(args, metrics)


if __name__ == "__main__":
    main()
