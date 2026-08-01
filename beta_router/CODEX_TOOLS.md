# βRouter Codex支援ツール

## `--repo` の意味

`--repo` は、各コマンドが調査・検索・差分確認・テストを行う対象の
Gitリポジトリルートです。現在の作業ディレクトリではなく、指定した
`--repo` を基準に解決します。

- `context`: 指定repoのGit状態、最近のファイル、テスト候補を取得する
- `search`: 指定repo以下だけを検索する
- `diff`: 指定repoのGit差分を表示する。親repoからはサブモジュール内部の
  差分ではなくコミットポインタだけが見えるため、内部差分は
  `--repo .../beta-kun-site` を指定する
- `test`: 指定repoが`beta-kun-site`自身なら`repo/beta_router`、親repoなら
  `repo/beta-kun-site/beta_router`を自動検出する

## 作業開始
python3 beta-kun-site/beta_router/codex_tools.py \
  --repo ~/python-study/my-dashboard \
  context

## 検索
python3 beta-kun-site/beta_router/codex_tools.py \
  --repo ~/python-study/my-dashboard \
  search "<検索語>"

高速な対象限定検索（`rg`があれば自動使用、なければPythonへfallback）:

```bash
python3 codex_tools.py --repo ~/python-study/my-dashboard \
  search "コルヒチン" --path data --ext py --ext json --max-results 50
```

`--path`はrepo相対で複数指定可能です。`--glob`、`--ext`、`--exclude`も
複数指定できます。repo外やrepo外へ出るsymlinkは拒否されます。

## 差分

staged、unstaged、untrackedを分離します。未追跡本文は`--untracked`時だけ、
ignored本文は明示pathと`--include-ignored`の組合せだけ表示します。

```bash
python3 codex_tools.py --repo ~/python-study/my-dashboard diff \
  --path data/pmda_dose_rule_stage6_colchicine_20260801.json --include-ignored

python3 codex_tools.py --repo ~/python-study/my-dashboard diff \
  --path data --untracked --max-files 10 --max-lines 500
```

秘密情報らしい名前、バイナリ、大容量ファイルはsummaryのみです。ツールは
ignored fileをstageしません。

## 作業終了

無関係なdiff/testを実行せず、終了レコードと同一task_idの軽量集計だけを記録します。

```bash
python3 beta-kun-site/beta_router/codex_tools.py \
  --repo ~/python-study/my-dashboard \
  --task-id "$BETA_TASK_ID" \
  --additional-instructions 0 --rework-count 0 finish
```

同一task_idで再度finishしても追記し、`duplicate_finish: true`と警告を出します。

## テスト
python3 beta-kun-site/beta_router/codex_tools.py \
  --repo ~/python-study/my-dashboard \
  test router

beta-kun-siteを直接repoにした場合も同じテストを実行できます。

```bash
cd ~/python-study/my-dashboard/beta-kun-site
python3 beta_router/codex_tools.py \
  --repo ~/python-study/my-dashboard/beta-kun-site \
  test router
```

## ルール
- 未コミット変更を消さない
- .envやAPIキーは触らない
- 編集後は必ず test router を実行
