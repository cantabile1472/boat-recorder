# 戦略X4（記録のみ・2026-11-14に条件固定）：戦略Yの買い目から、次の3つを除いたもの
#   1) 1Rの買い目が4点以上のレース（実運用と同じく3点まで）
#   2) 3連単から見たその組の確率が、200秒前→40秒前で2割以上落ちた組（log比 -0.2 以下）
#   3) 40秒前に3連単「3-2-1」が本来の2倍超買われているレースの 1-2-3（大口で3連複1-2-3が来やすく見えるため）
#  比較のため「Y（3点まで）」も並べて出す。条件はあとから変えないこと
#  python tools/strategy_x4.py [開始日]   … 既定は 20261111
import sys, os, pickle, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import strategy_y as Y

start = sys.argv[1] if len(sys.argv) > 1 else '20261111'
M = pickle.load(open(Y.MODEL, 'rb'))
X = Y.build(day_min=start)
if X.empty:
    print('戦略X4：まだ記録なし'); sys.exit()
X['qb'] = Y.sm(X[['lq', 'lw']].values @ M['w'], X.gid.values)
X['ev'] = X.qb * X.o3 * np.exp(M['q80'].predict(X[M['F']]))
K = ['day', 'jcd', 'R']


def r321(f, keep):
    """kyotei_odds_full の40秒前（snap 3）で、3-2-1 の売れ方 ÷ 1着確率から作った本来の線"""
    I = Y.P3.index((3, 2, 1)); out = {}
    d = pd.read_csv(f, dtype=str); d = d[(d.kind == '3t') & (d.snap == '3')]
    for j, R_, vals in zip(d.jcd, d.R, d['values']):
        if (int(j), int(R_)) not in keep:
            continue
        v = np.array([Y.num(x) for x in str(vals).split()])
        if len(v) != 120:
            continue
        inv = np.where(v > 0, 1 / np.where(v > 0, v, 1), 0)
        if inv.sum() <= 0:
            continue
        q = inv / inv.sum(); w = np.zeros(7)
        for (a, b, c), x in zip(Y.P3, q):
            w[a] += x
        h = np.array([w[a] * w[b] / max(1 - w[a], 1e-9) * w[c] / max(1 - w[a] - w[b], 1e-9) for a, b, c in Y.P3]); h /= h.sum()
        out[(int(j), int(R_))] = q[I] / h[I] if h[I] > 0 else np.nan
    return out


P = X[(X.o3 > 10) & (X.o3 <= 50) & (X.ev >= 1.0) & (X.ev < 1.2)].copy()
P['n'] = P.groupby(K).c.transform('count')
P = P[P.n <= 3].copy()
P['mom'] = np.log(P.q3 / P.q1)
R3 = {}
for day, g in P.groupby('day'):
    keep = set(zip(g.jcd, g.R))
    for (j, R_), v in r321(os.path.join(Y.ROOT, 'data', day, 'kyotei_odds_full.csv'), keep).items():
        R3[(day, j, R_)] = v
P['r321'] = [R3.get(k, np.nan) for k in zip(P.day, P.jcd, P.R)]
P['ex'] = (P.mom <= -0.2) | ((P.c == '1-2-3') & (P.r321 > 2))
P[K + ['c', 'o3', 'oc', 'qb', 'ev', 'mom', 'r321', 'ex', 'pay']].round(4).to_csv(os.path.join(Y.ROOT, 'data', 'x4_picks.csv'), index=False)


def line(t):
    return f"{len(t)}点 的中{int((t.pay > 0).sum())} 出資{len(t)*100:,}円 払戻{int(t.pay.sum()):,}円 回収{t.pay.mean():.0f}%" if len(t) else '0点'


print(f'# 戦略X4（記録のみ：Yの3点まで−急落−3-2-1歪み） {start}〜')
for d, t in P.groupby('day'):
    print(f'  {d}: Y(3点まで) {line(t)} ／ X4 {line(t[~t.ex])}（除外{int(t.ex.sum())}点・的中{int((t[t.ex].pay > 0).sum())}）')
print(f'Y(3点まで) 累計: {line(P)}')
print(f'戦略X4 累計: {line(P[~P.ex])}')
print(f'除外した分 累計: {line(P[P.ex])}')
