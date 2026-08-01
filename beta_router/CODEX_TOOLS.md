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
