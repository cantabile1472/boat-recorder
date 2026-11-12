# 戦略Y（記録のみ）：競艇3連複。40秒前に10〜50倍の組で、
#   確率＝3連単換算とワイドを混ぜたもの、締切オッズ＝80%点の予想 → EV1.0〜1.2 の組を買う
#  python tools/strategy_y.py train [最終日]   … models/y_trio.pkl（混ぜ方の重み＋80%点モデル）を作る
#  python tools/strategy_y.py [開始日]          … 固定モデルで各日を判定し、公開データの払戻で答え合わせ → data/y_picks.csv
import sys, os, glob, pickle, itertools, datetime, warnings; warnings.filterwarnings('ignore')
import numpy as np, pandas as pd
from scipy.optimize import minimize
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, '..')
MODEL = os.path.join(ROOT, 'models', 'y_trio.pkl')
PUB = '/home/claude/boatracecsv/boatracecsv.github.io/data/results/payouts/'
P3 = []
for i in range(120):
    a = i % 6 + 1; row = i // 6; o = [b for b in range(1, 7) if b != a]; b = o[row // 4]; o2 = [c for c in o if c != b]; P3.append((a, b, o2[row % 4]))
TRI = sorted(itertools.combinations(range(1, 7), 3), key=lambda t: (t[1], t[2], t[0]))
PAIR = [(a, b) for b in range(2, 7) for a in range(1, b)]
F = ['a', 'b', 'c3', 'has1', 'has6', 'jcd', 'hour', 'stale', 'lo', 'lq', 'lw', 'dw', 'gap', 'do1', 'do2', 'dq1', 'dq2', 'rk_o', 'rk_gap']


def num(v):
    try:
        return float(str(v).replace(',', '').split('-')[0])
    except Exception:
        return 0.0


def mins(a, b):
    try:
        return (datetime.datetime.strptime(str(b), '%H:%M') - datetime.datetime.strptime(str(a), '%H:%M')).total_seconds() / 60
    except Exception:
        return np.nan


def results(day):
    f = f'{PUB}{day[:4]}/{day[4:6]}/{day[6:]}.csv'; R = {}
    if not os.path.exists(f):
        return R
    p = pd.read_csv(f, dtype=str)
    for _, r in p.iterrows():
        c = r['レースコード']; k = r.get('3連複_組番')
        if isinstance(k, str):
            R[(int(c[8:10]), int(c[10:12]))] = (tuple(sorted(int(z) for z in k.split('='))), float(str(r['3連複_払戻金']).replace(',', '') or 0))
    return R


def build(day_min=None, day_max=None):
    rows = []
    for f in sorted(glob.glob(os.path.join(ROOT, 'data', '2026*', 'kyotei_odds_full.csv'))):
        day = f.split(os.sep)[-2]
        if (day_min and day < day_min) or (day_max and day > day_max):
            continue
        RES = results(day)
        if not RES:
            continue
        d = pd.read_csv(f, dtype=str); d = d[d.kind.isin(['3t', '3f', 'k'])]
        L = pd.read_csv(f.replace('kyotei_odds_full', 'kyotei_log')); L = L[L.boat == 1].drop_duplicates(['jcd', 'R', 'snap'])
        UP = {(int(r.jcd), int(r.R), int(r.snap)): (r.upd, r.deadline) for r in L.itertuples()}
        for (j, R), t in d.groupby(['jcd', 'R']):
            j = int(j); R = int(R); res = RES.get((j, R))
            if not res:
                continue
            sn = {}
            for s, u in t.groupby('snap'):
                try:
                    t3 = np.array([num(v) for v in u[u.kind == '3t']['values'].iloc[0].split()]); f3 = np.array([num(v) for v in u[u.kind == '3f']['values'].iloc[0].split()])
                except Exception:
                    continue
                if len(t3) != 120 or len(f3) != 20:
                    continue
                inv = np.where(t3 > 0, 1 / np.where(t3 > 0, t3, 1), 0)
                if inv.sum() <= 0:
                    continue
                q = inv / inv.sum(); tri = {}
                for (a, b, c), v in zip(P3, q):
                    kk = tuple(sorted((a, b, c))); tri[kk] = tri.get(kk, 0) + v
                try:
                    kw = [num(v) for v in u[u.kind == 'k']['values'].iloc[0].split()]
                except Exception:
                    kw = []
                wi = {pr: (1 / o if o > 0 else 1e-4) for pr, o in zip(PAIR, kw)} if len(kw) == 15 else {pr: np.nan for pr in PAIR}
                wsc = np.array([np.log(wi[(kk[0], kk[1])]) + np.log(wi[(kk[0], kk[2])]) + np.log(wi[(kk[1], kk[2])]) for kk in TRI])
                sn[s] = (f3, np.array([tri[kk] for kk in TRI]), wsc)
            if not all(s in sn for s in ('1', '2', '3', 'close')):
                continue
            upd, dl = UP.get((j, R, 3), (None, None))
            if dl is None:
                continue
            for i, kk in enumerate(TRI):
                oc = sn['close'][0][i]; o3 = sn['3'][0][i]
                if oc <= 0 or o3 <= 0:
                    continue
                r = dict(day=day, jcd=j, R=R, c='-'.join(map(str, kk)), a=kk[0], b=kk[1], c3=kk[2], win=int(kk == res[0]), oc=oc, hour=int(str(dl)[:2]), stale=mins(upd, dl), pay=res[1] if kk == res[0] else 0)
                for s in ('1', '2', '3'):
                    o = sn[s][0][i]; r[f'o{s}'] = o if o > 0 else np.nan; r[f'q{s}'] = sn[s][1][i]; r[f'w{s}'] = sn[s][2][i]
                rows.append(r)
    X = pd.DataFrame(rows); K = ['day', 'jcd', 'R']; g = X.groupby(K)
    for s in ('1', '2', '3'):
        X[f's{s}'] = (1 / X[f'o{s}']) / g[f'o{s}'].transform(lambda v: (1 / v).sum())
    X['y'] = np.log(X.oc / X.o3); X['lo'] = np.log(X.o3); X['lq'] = np.log(X.q3); X['gap'] = np.log(X.q3 / X.s3); X['lw'] = X.w3; X['dw'] = X.w3 - X.w2
    for a in ('1', '2'):
        X[f'do{a}'] = np.log(X.o3 / X[f'o{a}']); X[f'dq{a}'] = np.log(X.q3 / X[f'q{a}'])
    X['rk_o'] = g.o3.rank(); X['rk_gap'] = g.gap.rank(ascending=False); X['has1'] = (X.a == 1).astype(int); X['has6'] = (X.c3 == 6).astype(int)
    X['gid'] = X.groupby(K).ngroup()
    return X


def sm(z, g):
    z = z - pd.Series(z).groupby(g).transform('max').values; e = np.exp(z); return e / pd.Series(e).groupby(g).transform('sum').values


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'train':
        from sklearn.ensemble import HistGradientBoostingRegressor as H
        X = build(day_max=sys.argv[2] if len(sys.argv) > 2 else None); X = X[X.groupby('gid').win.transform('sum') == 1]
        wv = minimize(lambda w: -np.log(sm(X[['lq', 'lw']].values @ w, X.gid.values)[X.win.values == 1]).mean(), [1.0, 0.0], method='L-BFGS-B').x
        m80 = H(loss='quantile', quantile=0.8, max_iter=300, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=60).fit(X[F], X.y)
        pickle.dump({'w': wv, 'q80': m80, 'F': F, 'days': sorted(X.day.unique())}, open(MODEL, 'wb'))
        print('戦略Yのモデル 学習', X.day.min(), '〜', X.day.max(), len(X), '点 重み', np.round(wv, 3)); sys.exit()
    start = sys.argv[1] if len(sys.argv) > 1 else '20261111'
    M = pickle.load(open(MODEL, 'rb'))
    X = build(day_min=start)
    if X.empty:
        print('戦略Y：まだ記録なし'); sys.exit()
    X['qb'] = sm(X[['lq', 'lw']].values @ M['w'], X.gid.values); X['ev'] = X.qb * X.o3 * np.exp(M['q80'].predict(X[M['F']]))
    P = X[(X.o3 > 10) & (X.o3 <= 50) & (X.ev >= 1.0) & (X.ev < 1.2)]
    P[['day', 'jcd', 'R', 'c', 'o3', 'oc', 'qb', 'ev', 'pay']].round(4).to_csv(os.path.join(ROOT, 'data', 'y_picks.csv'), index=False)
    print(f'# 戦略Y（競艇3連複・40秒前に10〜50倍・EV1.0〜1.2、記録のみ） {start}〜')
    for d, t in P.groupby('day'):
        print(f"  {d}: {t.groupby(['jcd', 'R']).ngroups}R {len(t)}点 的中{int((t.pay > 0).sum())} 出資{len(t)*100:,}円 払戻{int(t.pay.sum()):,}円 回収{t.pay.mean():.0f}%")
    print(f"戦略Y 累計: {len(P)}点 的中{int((P.pay > 0).sum())} 出資{len(P)*100:,}円 払戻{int(P.pay.sum()):,}円 収支{int(P.pay.sum()) - len(P)*100:+,}円 回収{P.pay.mean():.0f}%")
