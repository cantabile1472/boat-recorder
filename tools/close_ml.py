# 締切オッズ予想 機械学習版：締切前スナップ（3分前/1分半前/40秒前/15秒前）の流れ＋表示の古さ＋3連単から締切単勝シェアを予想
#  python tools/close_ml.py [判定スナップ 3=40秒前 4=15秒前]
import pandas as pd, numpy as np, glob, sys, datetime
from sklearn.ensemble import HistGradientBoostingRegressor
S = int(sys.argv[1]) if len(sys.argv) > 1 else 3
SP = '/tmp/claude-0/-home-claude/2ac40992-b703-5112-9a19-f709de764321/scratchpad/'
rows = []
for f in sorted(glob.glob('data/2026*/kyotei_log.csv')):
    day = f.split('/')[1]; c = f.replace('kyotei_log', 'kyotei_close')
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
days = sorted(x.day.unique()); print(f'判定={S} 日数{len(days)} レース{x.groupby(K).ngroups} 艇{len(x)}')
# v1（式）：締切シェア=(今シェア+λ×3連単)/(1+λ) を学習日で当てはめ
def v1pred(tr, te):
    best = min(np.arange(0, 6, 0.1), key=lambda l: np.mean((np.log((tr[f's{S}'] + l * tr[f'q{S}']) / (1 + l)) - np.log(tr.s_close))**2))
    return np.log((te[f's{S}'] + best * te[f'q{S}']) / (1 + best) / te[f's{S}']), best
x['pred_v0'] = 0.0; x['pred_v1'] = np.nan; x['pred_ml'] = np.nan
for d in days:   # 1日ずつ抜いて検証（その日以外で学習）
    tr = x[x.day != d]; te = x.day == d
    x.loc[te, 'pred_v1'], lam = v1pred(tr, x[te])
    m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=40, categorical_features=[F.index('jcd')] if False else None)
    m.fit(tr[F], tr.y); x.loc[te, 'pred_ml'] = m.predict(x.loc[te, F])
x.to_pickle(SP + f'close_ml_{S}.pkl')
# 予想シェア→レース内で正規化→予想締切オッズ
def evaluate(col, label):
    sh = x[f's{S}'] * np.exp(x[col]); sh = sh / sh.groupby([x.day, x.jcd, x.R]).transform('sum')
    po = 0.75 / sh; e = np.abs(np.log(po / x.odds_close)); b1 = x.boat == 1
    evp = x[f'q{S}'] * po; tgt = x.p3_close * x.odds_close >= 1.2; pay = np.where(x.winner == x.boat, x.payout, 0)
    out = f'{label:10s} ±10%以内{(e<0.1).mean()*100:3.0f}% ±25%以内{(e<0.25).mean()*100:3.0f}% (1号艇±25% {(e[b1]<0.25).mean()*100:3.0f}%)'
    for th in (1.1, 1.2):
        m = evp >= th
        out += f' | 予想EV{th}+ {m.sum():4d}艇 当たり{tgt[m].mean()*100 if m.sum() else 0:3.0f}% 回収{pay[m].mean() if m.sum() else 0:4.0f}%'
    print(out)
    return evp
evaluate('pred_v0', '今のまま'); evaluate('pred_v1', 'v1式'); evp = evaluate('pred_ml', '機械学習')
x['evp'] = evp
tgt = x.p3_close * x.odds_close >= 1.2; pay = np.where(x.winner == x.boat, x.payout, 0)
print('予想EV上位で切った場合（機械学習）')
for q in (0.99, 0.98, 0.95, 0.9):
    t = x.evp.quantile(q); m = x.evp >= t
    print(f'  上位{(1-q)*100:.0f}% (予想EV{t:.2f}以上) {m.sum()}艇 当たり{tgt[m].mean()*100:.0f}% 回収{pay[m].mean():.0f}%')
m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=40).fit(x[F], x.y)
from sklearn.inspection import permutation_importance
pi = permutation_importance(m, x[F].sample(min(4000, len(x)), random_state=0), x.y.loc[x[F].sample(min(4000, len(x)), random_state=0).index], n_repeats=3, random_state=0)
print('効いてる特徴:', ', '.join(f'{F[i]}={pi.importances_mean[i]:.3f}' for i in np.argsort(-pi.importances_mean)[:10]))
