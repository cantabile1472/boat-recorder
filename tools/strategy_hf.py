# 戦略H（複勝）：モデル f70 ＝ 複勝の締切オッズ（下限）の「7割の確率でこれより下がらない底値」を予想
#   f70のEV ＝ 3連単換算の2着以内率 × 底値オッズ。0.7以上・1号艇除外・40秒前（スナップ3）で買い
#  python tools/strategy_hf.py train [最終日]  … kyotei_odds_full.csv（3t・tf のスナップ1〜3と close）から学習 → models/f70_3.pkl
#  レコーダーからは evaluate(full, upd, jcd, deadline) を呼ぶ。full = {スナップ: {'3t': [120個], 'tf': [12個]}}
import os, sys, glob, pickle, datetime
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, '..', 'models', 'f70_3.pkl')
_M = {}
P3 = []
for i in range(120):
    a = i % 6 + 1; row = i // 6; o = [b for b in range(1, 7) if b != a]; P3.append((a, o[row // 4]))


def _num(v):
    try:
        return float(str(v).replace(',', ''))
    except Exception:
        return 0.0


def _lo(v):
    try:
        return float(str(v).split('-')[0])
    except Exception:
        return 0.0


def _mins(a, b):
    try:
        return (datetime.datetime.strptime(str(b), '%H:%M') - datetime.datetime.strptime(str(a), '%H:%M')).total_seconds() / 60
    except Exception:
        return np.nan


def parse(t3, tf):
    """3連単120個・単複12個の文字列 → (複勝下限[6], 単勝[6], 2着以内率[6], 1着率[6])。読めなければ None"""
    t3 = np.array([_num(v) for v in t3]) if t3 is not None else None
    if t3 is None or len(t3) != 120 or tf is None or len(tf) != 12:
        return None
    inv = np.where(t3 > 0, 1 / np.where(t3 > 0, t3, 1), 0)
    if inv.sum() <= 0:
        return None
    q = inv / inv.sum(); top2 = np.zeros(7); win = np.zeros(7)
    for (a, b), v in zip(P3, q):
        top2[a] += v; top2[b] += v; win[a] += v
    return np.array([_lo(v) for v in tf[6:12]]), np.array([_num(v) for v in tf[:6]]), top2[1:], win[1:]


def race_rows(snaps, jcd, deadline, upd):
    """snaps = {'1':parse結果, '2':…, '3':…}（'close' があれば正解も入れる）→ 1艇1行の表"""
    rows = []
    for b in range(1, 7):
        f3 = snaps['3'][0][b - 1]
        if f3 <= 0:
            continue
        r = dict(boat=b, jcd=int(jcd), hour=int(str(deadline)[:2]), stale=_mins(upd, deadline))
        for s in ('1', '2', '3'):
            if s in snaps:
                fo, to, t2, w = snaps[s]
                r[f'f{s}'] = fo[b - 1] if fo[b - 1] > 0 else np.nan; r[f't{s}'] = to[b - 1] if to[b - 1] > 0 else np.nan; r[f'q{s}'] = t2[b - 1]; r[f'w{s}'] = w[b - 1]
            else:
                r[f'f{s}'] = r[f't{s}'] = r[f'q{s}'] = r[f'w{s}'] = np.nan
        if 'close' in snaps:
            r['fc'] = snaps['close'][0][b - 1]
        rows.append(r)
    return rows


def finish(X, K):
    g = X.groupby(K)
    X['lf'] = np.log(X.f3); X['lt'] = np.log(X.t3); X['lq'] = np.log(X.q3); X['lw'] = np.log(X.w3)
    X['ev3'] = X.q3 * X.f3; X['gapf'] = np.log(X.q3 * X.f3); X['gapt'] = np.log(X.w3 * X.t3)
    for a in ('1', '2'):
        X[f'df{a}'] = np.log(X.f3 / X[f'f{a}']); X[f'dq{a}'] = np.log(X.q3 / X[f'q{a}']); X[f'dt{a}'] = np.log(X.t3 / X[f't{a}'])
    X['rk_q'] = g.q3.rank(ascending=False); X['rk_ev'] = g.ev3.rank(ascending=False); X['qmax'] = g.w3.transform('max'); X['nb'] = g.boat.transform('count')
    return X


F = ['boat', 'jcd', 'hour', 'stale', 'lf', 'lt', 'lq', 'lw', 'gapf', 'gapt', 'df1', 'df2', 'dq1', 'dq2', 'dt1', 'dt2', 'rk_q', 'rk_ev', 'qmax', 'nb']


def build_train(day_max=None):
    rows = []
    for f in sorted(glob.glob(os.path.join(HERE, '..', 'data', '2026*', 'kyotei_odds_full.csv'))):
        day = f.split(os.sep)[-2]
        if day_max and day > day_max:
            continue
        d = pd.read_csv(f, dtype=str); d = d[d.kind.isin(['3t', 'tf'])]
        L = pd.read_csv(f.replace('kyotei_odds_full', 'kyotei_log')); L = L[L.boat == 1].drop_duplicates(['jcd', 'R', 'snap'])
        UP = {(int(r.jcd), int(r.R), int(r.snap)): (r.upd, r.deadline) for r in L.itertuples()}
        for (j, R), t in d.groupby(['jcd', 'R']):
            snaps = {}
            for s, u in t.groupby('snap'):
                try:
                    pz = parse(u[u.kind == '3t']['values'].iloc[0].split(), u[u.kind == 'tf']['values'].iloc[0].split())
                except Exception:
                    pz = None
                if pz is not None:
                    snaps[s] = pz
            if not all(s in snaps for s in ('1', '2', '3', 'close')):
                continue
            upd, dl = UP.get((int(j), int(R), 3), (None, None))
            if dl is None:
                continue
            for r in race_rows(snaps, j, dl, upd):
                if r.get('fc', 0) > 0:
                    r.update(day=day, R=int(R)); rows.append(r)
    X = finish(pd.DataFrame(rows), ['day', 'jcd', 'R'])
    X['y'] = np.log(X.fc / X.f3)
    return X


def evaluate(full, upd, jcd, deadline, th=0.7, exclude=(1,)):
    """戻り値 (全艇の表, 買い目の艇リスト)。モデルが無い・データ不足なら (None, [])"""
    if 'm' not in _M:
        _M['m'] = pickle.load(open(MODEL, 'rb')) if os.path.exists(MODEL) else None
    M = _M['m']
    if M is None:
        return None, []
    snaps = {}
    for s in (1, 2, 3):
        v = full.get(s)
        if v:
            pz = parse(v.get('3t'), v.get('tf'))
            if pz is not None:
                snaps[str(s)] = pz
    if '3' not in snaps:
        return None, []
    X = pd.DataFrame(race_rows(snaps, jcd, deadline, upd))
    if X.empty:
        return None, []
    X['race'] = 0; X = finish(X, ['race'])
    X['f70_odds'] = X.f3 * np.exp(M['q30'].predict(X[M['F']])); X['f70_ev'] = X.q3 * X.f70_odds
    return X, [int(b) for b in X.boat[(X.f70_ev >= th) & ~X.boat.isin(list(exclude))]]


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'train':
        from sklearn.ensemble import HistGradientBoostingRegressor as H
        P = dict(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=40)
        X = build_train(sys.argv[2] if len(sys.argv) > 2 else None)
        M = {'F': F, 'q30': H(loss='quantile', quantile=0.3, **P).fit(X[F], X.y), 'mean': H(**P).fit(X[F], X.y), 'days': sorted(X.day.unique()), 'n': len(X)}
        pickle.dump(M, open(MODEL, 'wb')); print('f70 学習', M['days'][0], '〜', M['days'][-1], len(X), '艇 →', MODEL)
