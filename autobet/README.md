# 自動投票（テレボート）のセットアップ手順

## 0. 用意するもの
- 日本のVPS 1台（さくらのVPS 1Gプラン か ConoHa VPS 1GB、Ubuntu 24.04 を選ぶ）。月700〜1,000円。
- テレボートの 加入者番号・暗証番号・認証番号
- ntfy のトピック名を2つ：今の通知用（既にある）と、注文用（新しく決める。長くて推測されない名前。例 `kanta-order-7f3k9d2x`）

## 1. GitHub側：注文用トピックを登録
- リポジトリの Settings → Secrets and variables → Actions → New repository secret
- 名前 `ORDER_TOPIC`、値は注文用トピック名
- これで記録プログラムがGの判定時に注文を流すようになる（次の起動から）

## 2. VPSにログインして準備（1回だけ）
```
sudo apt update && sudo apt install -y python3-pip git
pip3 install --break-system-packages playwright
python3 -m playwright install --with-deps chromium
git clone https://github.com/cantabile1472/boat-recorder.git
cd boat-recorder/autobet
cp settings.example.json settings.json
nano settings.json      # トピック名・テレボートの番号・金額を入れる（mode は dry のまま）
```

## 3. 空撃ちテスト
```
python3 autobet.py test
```
- `shots/` に画面（png）とHTMLが保存される。ログイン→投票画面→入力まで進めたかを png で確認。
- うまく進めない場合は shots の html と png を送ってもらえれば、`selectors.json` を合わせる。
- 本物のレースで空撃ちさせる場合は `python3 autobet.py` を動かしたまま、通知Gが来るのを待つ（購入ボタンは押さない）。

## 4. 常駐させる
```
sudo cp autobet.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now autobet
journalctl -u autobet -f      # ログを見る
```

## 5. 本番に切り替える
- `settings.json` の `"mode": "live"` にする
- `touch RUN` で RUN ファイルを作る（これが無いと絶対に買わない）
- `sudo systemctl restart autobet`

## 止め方（いつでも）
- スマホから ntfy の注文トピックに「停止」と送る → それ以降は買わない（「再開」で戻る）
- または VPS で `touch STOP`
- 完全に止める：`sudo systemctl stop autobet`

## 安全装置
- 1点の金額（通常/★）と1日の上限は settings.json で固定
- 同じレースには1回しか買わない
- 締切まで15秒を切っていたら見送り
- 購入結果が確認できなかったときは「要確認」の通知を出す（テレボートの投票履歴で確認）
- 全ての動きは logs/日付.log に残る
