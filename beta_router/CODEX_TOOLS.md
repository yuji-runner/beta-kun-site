# βRouter Codex支援ツール

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

## ルール
- 未コミット変更を消さない
- .envやAPIキーは触らない
- 編集後は必ず test router を実行
