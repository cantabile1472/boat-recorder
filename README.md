# boat-recorder

競艇・オートレースの「締切前のオッズ」と「締切のオッズ」「結果」を記録するツール（お金は賭けない記録用）。

- GitHub Actions で毎日 8:05 / 13:45 / 19:20（日本時間）に自動で動く
- 締切の 3分前・1分半前・40秒前・15秒前・5秒前 のオッズを記録
- 記録は `data/日付/` に保存
  - `kyotei_log.csv` / `kyotei_close.csv`（競艇）
  - `auto_log.csv` / `auto_close.csv`（オート）
- 戦略Aの設定は `config.json`
- スマホ通知は、リポジトリの Secrets に `NTFY_TOPIC` を入れると届く
