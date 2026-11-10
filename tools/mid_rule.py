# 「中間の艇・予想EV1以上」ルールの前向き検証（記録だけ、通知しない）
#  python tools/mid_rule.py train        … 11/9までのデータでモデルを学習して models/ に固定保存
#  python tools/mid_rule.py [開始日]      … 固定モデルで 11/10 以降の各日を判定し data/mid_picks.csv と成績を出す
import sys, os, pickle, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__)); import close_feat
from sklearn.ensemble import HistGradientBoostingRegressor
CUT = '20261109'; LAB = {3: '40秒前', 4: '15秒前'}


def pick(x, S, m, F):
    K = [x.day, x.jcd, x.R]
    sh = x[f's{S}'] * np.exp(m.predict(x[F])); sh = sh / sh.groupby(K).transform('sum')
    x['po'] = 0.75 / sh; x['ev'] = x[f'q{S}'] * x.po
    vol = (x.rk_s > 5) | (x.po > 50) | (x.boat == 6) | (x.clsn == 1)      # 荒れやすい艇
    stb = (x.boat == 1) | (x.rk_s == 1) | (x.clsn == 4) | (x.hour >= 17)  # 荒れにくい艇
    x['mid'] = ~vol & ~stb
    return x[x.mid & (x.ev >= 1)]


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'train':
        for S in (3, 4):
            x, F = close_feat.build(S, day_max=CUT)
            m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=40).fit(x[F], x.y)
            pickle.dump({'model': m, 'F': F, 'cut': CUT, 'n': len(x)}, open(f'models/close_ml_{S}.pkl', 'wb'))
            print(S, '学習', len(x), '艇 → models/close_ml_%d.pkl' % S)
        sys.exit()
    start = sys.argv[1] if len(sys.argv) > 1 else '20261110'
    rows = []
    for S in (3, 4):
        M = pickle.load(open(f'models/close_ml_{S}.pkl', 'rb'))
        try:
            x, _ = close_feat.build(S, day_min=start)
        except Exception as e:
            print('データなし', e); continue
        p = pick(x, S, M['model'], M['F'])
        p = p.assign(判定=LAB[S], pay=np.where(p.winner == p.boat, p.payout, 0))
        rows.append(p[['day', '判定', 'jcd', 'R', 'boat', f'odds{S}', 'po', 'ev', 'odds_close', 'winner', 'pay']].rename(columns={f'odds{S}': 'odds_now'}))
    if not rows:
        sys.exit()
    P = pd.concat(rows).sort_values(['day', 'jcd', 'R', '判定'])
    P.round(3).to_csv('data/mid_picks.csv', index=False)
    print(f'# 中間の艇・予想EV1以上（記録のみ） {start}〜')
    for j, g in P.groupby('判定'):
        print(f"{j}: {len(g)}艇 的中{(g.pay > 0).sum()} 回収{g.pay.mean():.0f}%  ／ 日別 " + ' '.join(f"{d[4:]}:{int(t.pay.sum())}/{len(t)*100}" for d, t in g.groupby('day')))
