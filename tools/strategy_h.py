# 戦略H：s70（締切オッズの70%点＝7割の確率でこれより下がらない底値を予想するモデル）で
#        「3連単換算の勝率 × 底値オッズ」が 0.85 以上の艇を買う。判定は40秒前（スナップ3）、対象は全艇。
#  python tools/strategy_h.py train [学習の最終日YYYYMMDD]  … models/s70_3.pkl を作る
#  レコーダーからは evaluate() を呼ぶ
import os, sys, pickle, datetime
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, '..', 'models', 's70_3.pkl')
S = 3
_M = {}


def _mins(a, b):
    try:
        ta = datetime.datetime.strptime(str(a), '%H:%M'); tb = datetime.datetime.strptime(str(b), '%H:%M'); return (tb - ta).total_seconds() / 60
    except Exception:
        return np.nan


def features(hist, info, jcd, deadline):
    """hist = {スナップ番号: {'od': {艇: 単勝オッズ}, 'p3': {艇: 3連単換算}, 'upd': 'H:MM'}}（1〜3）
       info = {艇: (級別, 全国勝率, 展示タイム)}。6艇そろっていなければ None"""
    h3 = hist.get(S)
    if not h3 or sum(1 for b in range(1, 7) if (h3['od'].get(b) or 0) > 0 and (h3['p3'].get(b) or 0) > 0) < 6:
        return None
    x = pd.DataFrame({'boat': range(1, 7)})
    for k in range(1, S + 1):
        hk = hist.get(k) or {'od': {}, 'p3': {}}
        o = np.array([hk['od'].get(b) or 0 for b in range(1, 7)], float); p = np.array([hk['p3'].get(b) or 0 for b in range(1, 7)], float)
        o[o <= 0] = np.nan; p[p <= 0] = np.nan
        inv = 1 / o; x[f'odds{k}'] = o
        x[f's{k}'] = inv / np.nansum(inv) if np.isfinite(inv).any() else np.nan
        x[f'q{k}'] = p / np.nansum(p) if np.isfinite(p).any() else np.nan
    x['stale'] = _mins((hist.get(S) or {}).get('upd'), deadline)
    x['stale_prev'] = _mins((hist.get(S - 1) or {}).get('upd'), deadline)
    x['hour'] = int(str(deadline)[:2]); x['jcd'] = int(jcd)
    x['gap'] = np.log(x[f'q{S}'] / x[f's{S}'])
    for a, b in [(1, 2), (2, 3)]:
        x[f'ds{a}{b}'] = np.log(x[f's{b}'] / x[f's{a}']); x[f'dq{a}{b}'] = np.log(x[f'q{b}'] / x[f'q{a}'])
    x['ls'] = np.log(x[f's{S}']); x['lq'] = np.log(x[f'q{S}'])
    x['rk_s'] = x[f's{S}'].rank(ascending=False); x['rk_gap'] = x.gap.rank(ascending=False)
    x['qmax'] = x[f'q{S}'].max(); x['ent'] = -(x[f'q{S}'] * np.log(x[f'q{S}'])).sum()
    cls = [(info.get(b) or ('', np.nan, np.nan))[0] for b in range(1, 7)]
    nat = [(info.get(b) or ('', np.nan, np.nan))[1] for b in range(1, 7)]
    ten = [(info.get(b) or ('', np.nan, np.nan))[2] for b in range(1, 7)]
    x['clsn'] = pd.Series(cls).map({'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}).values
    nat = pd.to_numeric(pd.Series(nat), errors='coerce'); x['nat_d'] = (nat - nat.mean()).values
    x['tenji_rk'] = pd.to_numeric(pd.Series(ten), errors='coerce').rank().values
    return x


def predict(x, M):
    a = x[f's{S}'] * np.exp(M['mean'].predict(x[M['F']])); tot = a.sum()
    b = x[f's{S}'] * np.exp(M['q70'].predict(x[M['F']]))
    x['pred_odds'] = 0.75 / (a / tot)                       # 締切オッズの予想（平均）
    x['s70_odds'] = 0.75 / (b / (tot - a + b))              # 底値オッズ（70%点）
    x['s70_ev'] = x[f'q{S}'] * x.s70_odds
    return x


def evaluate(hist, info, jcd, deadline, th=0.85):
    """戦略Hの判定。戻り値 (全6艇の表, 買い目の艇リスト)。モデルが無い・6艇そろわない場合は (None, [])"""
    if 'm' not in _M:
        _M['m'] = pickle.load(open(MODEL, 'rb')) if os.path.exists(MODEL) else None
    M = _M['m']
    if M is None:
        return None, []
    x = features(hist, info, jcd, deadline)
    if x is None:
        return None, []
    x = predict(x, M)
    return x, [int(b) for b in x.boat[x.s70_ev >= th]]


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'train':
        sys.path.insert(0, HERE); import close_feat
        from sklearn.ensemble import HistGradientBoostingRegressor as H
        P = dict(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=40)
        last = sys.argv[2] if len(sys.argv) > 2 else None
        x, F = close_feat.build(S, day_max=last)
        M = {'F': F, 'mean': H(**P).fit(x[F], x.y), 'q70': H(loss='quantile', quantile=0.7, **P).fit(x[F], x.y),
             'days': sorted(x.day.unique()), 'n': len(x)}
        pickle.dump(M, open(MODEL, 'wb'))
        print('s70 学習', M['days'][0], '〜', M['days'][-1], len(x), '艇 →', MODEL)
