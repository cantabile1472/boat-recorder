# オート版s70（記録のみ）：42秒前（スナップ3）に、3連単換算×底値オッズ（締切オッズの70%点）が 0.9 以上の車を記録
#  python tools/strategy_h_auto.py train [学習の最終日]  … models/s70_auto_3.pkl を作る
#  レコーダーからは evaluate() を呼ぶ。hist = {スナップ: {'od': {車: オッズ}, 'p3': {車: 換算}, 'votes': 票数}}
import os, sys, pickle
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, '..', 'models', 's70_auto_3.pkl')
S = 3
_M = {}


def features(hist, pc, deadline):
    h = hist.get(S)
    if not h:
        return None
    cars = sorted(c for c in h['od'] if (h['od'].get(c) or 0) > 0 and (h['p3'].get(c) or 0) > 0)
    if len(cars) < 5:
        return None
    x = pd.DataFrame({'car': cars})
    for k in range(1, S + 1):
        hk = hist.get(k) or {'od': {}, 'p3': {}, 'votes': np.nan}
        o = np.array([hk['od'].get(c) or 0 for c in cars], float); p = np.array([hk['p3'].get(c) or 0 for c in cars], float)
        o[o <= 0] = np.nan; p[p <= 0] = np.nan
        x[f'odds{k}'] = o
        x[f's{k}'] = (1 / o) / np.nansum(1 / o) if np.isfinite(o).any() else np.nan
        x[f'q{k}'] = p / np.nansum(p) if np.isfinite(p).any() else np.nan
        x[f'votes{k}'] = hk.get('votes', np.nan)
    x['nh'] = len(cars); x['pc'] = int(pc); x['hour'] = int(str(deadline)[:2])
    x['gap'] = np.log(x[f'q{S}'] / x[f's{S}'])
    for a in range(1, S):
        x[f'ds{a}{S}'] = np.log(x[f's{S}'] / x[f's{a}']); x[f'dq{a}{S}'] = np.log(x[f'q{S}'] / x[f'q{a}'])
    x['ls'] = np.log(x[f's{S}']); x['lq'] = np.log(x[f'q{S}'])
    x['rk_s'] = x[f's{S}'].rank(ascending=False); x['rk_gap'] = x.gap.rank(ascending=False)
    x['qmax'] = x[f'q{S}'].max(); x['ent'] = -(x[f'q{S}'] * np.log(x[f'q{S}'])).sum()
    v3 = pd.to_numeric(x[f'votes{S}'], errors='coerce').clip(lower=1); v1 = pd.to_numeric(x['votes1'], errors='coerce').clip(lower=1)
    x['lvotes'] = np.log(v3); x['vgrow'] = np.log(v3 / v1)
    return x


def evaluate(hist, pc, deadline, th=0.9):
    if 'm' not in _M:
        _M['m'] = pickle.load(open(MODEL, 'rb')) if os.path.exists(MODEL) else None
    M = _M['m']
    x = features(hist, pc, deadline) if M else None
    if x is None:
        return None, []
    a = x[f's{S}'] * np.exp(M['mean'].predict(x[M['F']])); tot = a.sum()
    b = x[f's{S}'] * np.exp(M['q70'].predict(x[M['F']]))
    x['pred_odds'] = 0.75 / (a / tot); x['s70_odds'] = 0.75 / (b / (tot - a + b)); x['s70_ev'] = x[f'q{S}'] * x.s70_odds
    return x, [int(c) for c in x.car[x.s70_ev >= th]]


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'train':
        sys.path.insert(0, HERE); import auto_close_feat
        from sklearn.ensemble import HistGradientBoostingRegressor as H
        P = dict(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=30)
        x, F = auto_close_feat.build(S, day_max=sys.argv[2] if len(sys.argv) > 2 else None)
        M = {'F': F, 'mean': H(**P).fit(x[F], x.y), 'q70': H(loss='quantile', quantile=0.7, **P).fit(x[F], x.y), 'days': sorted(x.day.unique()), 'n': len(x)}
        pickle.dump(M, open(MODEL, 'wb')); print('s70オート版 学習', M['days'][0], '〜', M['days'][-1], len(x), '車')
