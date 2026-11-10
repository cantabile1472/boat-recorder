# オート：締切前スナップ（auto_close.csv の odds1〜5・p3_1〜5・votes1〜5）から締切オッズ予想用の表を作る
#  スナップ: 1=3分20秒前 2=1分35秒前 3=42秒前 4=17秒前 5=7秒前（競艇と同じ）
import glob, numpy as np, pandas as pd


def build(S=3, day_min=None, day_max=None):
    rows = []
    for f in sorted(glob.glob('data/2026*/auto_close.csv')):
        day = f.split('/')[1]
        if (day_min and day < day_min) or (day_max and day > day_max):
            continue
        c = pd.read_csv(f); c['day'] = day
        lg = f.replace('auto_close', 'auto_log')
        try:
            L = pd.read_csv(lg, usecols=['pc', 'R', 'deadline']).drop_duplicates(['pc', 'R'])
            c = c.merge(L, on=['pc', 'R'], how='left')
        except Exception:
            c['deadline'] = np.nan
        rows.append(c)
    x = pd.concat(rows).drop_duplicates(['day', 'pc', 'R', 'car'], keep='last')
    ok = (x[f'odds{S}'] > 0) & (x.odds_close > 0) & (x[f'p3_{S}'] > 0)
    x = x[ok].copy()
    K = ['day', 'pc', 'R']; x['nh'] = x.groupby(K).car.transform('count'); x = x[x.nh >= 5]
    g = lambda c: x.groupby(K)[c]
    for k in list(range(1, S + 1)) + ['_close']:
        o = f'odds{k}' if k != '_close' else 'odds_close'; p = f'p3_{k}' if k != '_close' else 'p3_close'
        x.loc[~(x[o] > 0), o] = np.nan; x.loc[~(x[p] > 0), p] = np.nan
        x[f's{k}'] = (1 / x[o]) / g(o).transform(lambda s: (1 / s).sum())
        x[f'q{k}'] = x[p] / g(p).transform('sum')
    x['y'] = np.log(x.s_close / x[f's{S}'])
    x['gap'] = np.log(x[f'q{S}'] / x[f's{S}'])
    for a in range(1, S):
        x[f'ds{a}{S}'] = np.log(x[f's{S}'] / x[f's{a}']); x[f'dq{a}{S}'] = np.log(x[f'q{S}'] / x[f'q{a}'])
    x['ls'] = np.log(x[f's{S}']); x['lq'] = np.log(x[f'q{S}'])
    x['rk_s'] = g(f's{S}').rank(ascending=False); x['rk_gap'] = g('gap').rank(ascending=False)
    x['qmax'] = g(f'q{S}').transform('max'); x['ent'] = -g(f'q{S}').transform(lambda s: (s * np.log(s)).sum())
    x['lvotes'] = np.log(x[f'votes{S}'].clip(1)); x['vgrow'] = np.log(x[f'votes{S}'].clip(1) / x['votes1'].clip(1))
    x['hour'] = pd.to_numeric(x.deadline.astype(str).str[:2], errors='coerce')
    F = ['car', 'nh', 'pc', 'hour', 'ls', 'lq', 'gap', 'rk_s', 'rk_gap', 'qmax', 'ent', 'lvotes', 'vgrow'] + [c for c in x.columns if c.startswith('ds') or c.startswith('dq')]
    return x, F
