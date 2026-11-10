# 締切オッズ予想の特徴作り（close_ml.py から切り出し）。build(S, days=None) → (x, F)
import pandas as pd, numpy as np, glob, sys, datetime

def build(S, day_min=None, day_max=None):
    rows = []
    for f in sorted(glob.glob('data/2026*/kyotei_log.csv')):
        day = f.split('/')[1]; c = f.replace('kyotei_log', 'kyotei_close')
        if (day_min and day < day_min) or (day_max and day > day_max):
            continue
        try:
            L = pd.read_csv(f); C = pd.read_csv(c)
        except Exception:
            continue
        try:
            I = pd.read_csv(f.replace('kyotei_log', 'kyotei_info'))
        except Exception:
            I = pd.DataFrame(columns=['jcd', 'R', 'boat', 'cls', 'nat', 'tenji'])
        L['day'] = day; C['day'] = day; I['day'] = day
        rows.append((L, C, I))
    L = pd.concat([r[0] for r in rows]); C = pd.concat([r[1] for r in rows]); I = pd.concat([r[2] for r in rows])
    L = L.drop_duplicates(['day', 'jcd', 'R', 'boat', 'snap'], keep='last')
    W = L.pivot_table(index=['day', 'jcd', 'R', 'boat'], columns='snap', values=['odds', 'p3'], aggfunc='last')
    W.columns = [f'{a}{b}' for a, b in W.columns]; W = W.reset_index()
    U = L[L.boat == 1].pivot_table(index=['day', 'jcd', 'R'], columns='snap', values='upd', aggfunc='last'); U.columns = [f'upd{b}' for b in U.columns]; U = U.reset_index()
    D = L[L.boat == 1].groupby(['day', 'jcd', 'R']).deadline.first().reset_index()
    x = W.merge(C[['day', 'jcd', 'R', 'boat', 'winner', 'payout', 'odds_close', 'p3_close']], on=['day', 'jcd', 'R', 'boat']).merge(U, on=['day', 'jcd', 'R']).merge(D, on=['day', 'jcd', 'R'])
    x = x.merge(I[['day', 'jcd', 'R', 'boat', 'cls', 'nat', 'tenji']], on=['day', 'jcd', 'R', 'boat'], how='left')
    ok = (x[f'odds{S}'] > 0) & (x.odds_close > 0) & (x[f'p3{S}'] > 0)
    for k in range(1, S):
        x.loc[~(x[f'odds{k}'] > 0), f'odds{k}'] = np.nan; x.loc[~(x[f'p3{k}'] > 0), f'p3{k}'] = np.nan
    cnt = x[ok].groupby(['day', 'jcd', 'R']).boat.transform('count'); x = x[ok][cnt == 6].copy()
    K = ['day', 'jcd', 'R']; g = lambda c: x.groupby(K)[c]
    for k in list(range(1, S + 1)) + ['_close']:
        o = f'odds{k}'; p = f'p3{k}' if k != '_close' else 'p3_close'
        x[f's{k}'] = (1 / x[o]) / g(o).transform(lambda s: (1 / s).sum())
        x[f'q{k}'] = x[p] / g(p).transform('sum')
    x['y'] = np.log(x.s_close / x[f's{S}'])
    def mins(a, b):
        try:
            ta = datetime.datetime.strptime(str(a), '%H:%M'); tb = datetime.datetime.strptime(str(b), '%H:%M'); return (tb - ta).total_seconds() / 60
        except Exception:
            return np.nan
    x['stale'] = [mins(u, d) for u, d in zip(x[f'upd{S}'], x.deadline)]          # 表示オッズの集計時刻が締切の何分前か
    x['stale_prev'] = [mins(u, d) for u, d in zip(x[f'upd{S-1}'], x.deadline)]
    x['hour'] = x.deadline.str[:2].astype(int)
    x['gap'] = np.log(x[f'q{S}'] / x[f's{S}'])
    for a, b in [(1, 2), (2, 3), (3, 4)]:
        if b <= S:
            x[f'ds{a}{b}'] = np.log(x[f's{b}'] / x[f's{a}']); x[f'dq{a}{b}'] = np.log(x[f'q{b}'] / x[f'q{a}'])
    x['ls'] = np.log(x[f's{S}']); x['lq'] = np.log(x[f'q{S}'])
    x['rk_s'] = g(f's{S}').rank(ascending=False); x['rk_gap'] = g('gap').rank(ascending=False)
    x['qmax'] = g(f'q{S}').transform('max'); x['ent'] = -g(f'q{S}').transform(lambda s: (s * np.log(s)).sum())
    x['clsn'] = x.cls.map({'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}); x['nat_d'] = x.nat - g('nat').transform('mean')
    x['tenji_rk'] = g('tenji').rank()
    x['gap_rest'] = x.gap - g('gap').transform('mean')
    F = ['boat', 'ls', 'lq', 'gap', 'rk_s', 'rk_gap', 'qmax', 'ent', 'stale', 'stale_prev', 'hour', 'jcd', 'clsn', 'nat_d', 'tenji_rk'] + [c for c in x.columns if c.startswith('ds') or c.startswith('dq')]

    return x, F