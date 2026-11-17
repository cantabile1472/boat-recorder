# 戦略Y3・Y3b（記録のみ）：戦略Y2の買い目から「一番来なさそうな艇」を含む組を除く
#   一番来なさそうな艇＝40秒前の3連単オッズから計算した「3着以内に入る確率」が6艇で一番低い艇
#   Y3 ：その艇を含む組をすべて除く
#   Y3b：その艇の3着以内率が20%未満のときだけ、その艇を含む組を除く
#  11/17に条件固定。11/18以降が本当の検証（11/4〜16は条件を決めるときに見た期間）
#  比較のため Y（3点まで）・Y2 も並べて出す。条件はあとから変えないこと
#  python tools/strategy_y3.py [開始日] [終了日]   … 既定は 20261118〜
import sys, os, glob, pickle, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import strategy_y as Y

start = sys.argv[1] if len(sys.argv) > 1 else '20261118'
end = sys.argv[2] if len(sys.argv) > 2 else None
M = pickle.load(open(Y.MODEL, 'rb'))
K = ['day', 'jcd', 'R']


def picks(fix):
    X = Y.build(day_min=start, day_max=end, fix321=fix)
    if X.empty:
        return X
    X['qb'] = Y.sm(X[['lq', 'lw']].values @ M['w'], X.gid.values)
    X['ev'] = X.qb * X.o3 * np.exp(M['q80'].predict(X[M['F']]))
    P = X[(X.o3 > 10) & (X.o3 <= 50) & (X.ev >= 1.0) & (X.ev < 1.2)].copy()
    P['n'] = P.groupby(K).c.transform('count')
    P = P[P.n <= 3].copy()
    P['mom'] = np.log(P.q3 / P.q1)
    return P


def weakest(days):
    """40秒前（snap 3）の3連単から、各レースの一番来なさそうな艇とその3着以内率"""
    out = {}
    for day in days:
        f = os.path.join(Y.ROOT, 'data', str(day), 'kyotei_odds_full.csv')
        if not os.path.exists(f):
            continue
        d = pd.read_csv(f, dtype=str); d = d[(d.kind == '3t') & (d.snap == '3')]
        for j, R_, vals in zip(d.jcd, d.R, d['values']):
            v = np.array([Y.num(x) for x in str(vals).split()])
            if len(v) != 120:
                continue
            inv = np.where(v > 0, 1 / np.where(v > 0, v, 1), 0)
            if inv.sum() <= 0:
                continue
            q = inv / inv.sum(); p = np.zeros(7)
            for (a, b, c), x in zip(Y.P3, q):
                p[a] += x; p[b] += x; p[c] += x
            p[0] = 9; w = int(np.argmin(p))
            out[(str(day), int(j), int(R_))] = (w, p[w])
    return out


Yb = picks(False)
P = picks(True)
if P.empty:
    print('戦略Y3：まだ記録なし'); sys.exit()
P = P[~(P.mom <= -0.2)].copy()                     # ここまでが Y2
W = weakest(sorted(set(P.day.astype(str)) | set(Yb.day.astype(str))))
P['kb'] = [W.get((str(d), int(j), int(r)), (0, 1))[0] for d, j, r in zip(P.day, P.jcd, P.R)]
P['kp'] = [W.get((str(d), int(j), int(r)), (0, 1))[1] for d, j, r in zip(P.day, P.jcd, P.R)]
P['hk'] = [str(k) in c.split('-') for k, c in zip(P.kb, P.c)]
P['y3'] = ~P.hk
P['y3b'] = ~(P.hk & (P.kp < 0.2))
P[K + ['c', 'o3', 'oc', 'qb', 'ev', 'kb', 'kp', 'y3', 'y3b', 'pay']].round(4).to_csv(os.path.join(Y.ROOT, 'data', 'y3_picks.csv'), index=False)


def line(t):
    return f"{len(t)}点 的中{int((t.pay > 0).sum())} 的中率{(t.pay > 0).mean():.1%} 回収{t.pay.mean():.0f}%" if len(t) else '0点'


print(f'# 戦略Y3・Y3b（記録のみ：Y2から一番来なさそうな艇を含む組を除く） {start}〜')
for d in sorted(set(P.day)):
    t = P[P.day == d]; y = Yb[Yb.day == d]
    print(f'  {d}: Y(3点まで) {line(y)} ／ Y2 {line(t)} ／ Y3 {line(t[t.y3])} ／ Y3b {line(t[t.y3b])}')
print(f'Y(3点まで) 累計: {line(Yb)}')
print(f'戦略Y2 累計: {line(P)}')
print(f'戦略Y3 累計: {line(P[P.y3])}（除いた分 {line(P[~P.y3])}）')
print(f'戦略Y3b 累計: {line(P[P.y3b])}（除いた分 {line(P[~P.y3b])}）')
