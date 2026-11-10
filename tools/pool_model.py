# 単勝の確定票数を予想するモデル（その時点で使える情報だけ）
#  特徴: 場・R・曜日・締切時刻・グレード・日次・ナイター・レース名、過去4週の同場同Rの票数、当日の前Rまでの票数（売れ行き）、出走表の強さ
import pandas as pd, numpy as np, glob, re
from sklearn.ensemble import HistGradientBoostingRegressor
SP = '/tmp/claude-0/-home-claude/2ac40992-b703-5112-9a19-f709de764321/scratchpad/'
T = '/home/claude/boatracecsv/boatracecsv.github.io/data/programs/title/2026/'
V = []
for f in sorted(glob.glob('data/bcvote/*.csv.gz')):
    d = pd.read_csv(f); day = f.split('/')[-1][:8]
    for r in d.itertuples():
        try:
            V.append((day, int(r.jo), int(r.R), sum(int(t) for t in str(r.hyousu1).split('|')[6].split()[:6])))
        except Exception:
            pass
V = pd.DataFrame(V, columns=['day', 'jcd', 'R', 'final']); V = V[V.final > 0]
tt = pd.concat([pd.read_csv(f, dtype=str) for f in sorted(glob.glob(T + '*/*.csv'))])
tt['day'] = tt['レース日'].str.replace('-', ''); tt['jcd'] = tt['レース場コード'].astype(int); tt['R'] = tt['レース回'].str.replace('R', '').astype(int)
tt['hour'] = pd.to_numeric(tt['電話投票締切予定'].str[:2], errors='coerce') + pd.to_numeric(tt['電話投票締切予定'].str[3:5], errors='coerce') / 60
tt['nichi'] = tt['日次'].str.replace('　', '').map({'初日': 1, '２日目': 2, '３日目': 3, '４日目': 4, '５日目': 5, '６日目': 6, '７日目': 7, '最終日': 9}).fillna(0)
tt['grade'] = tt['グレード'].fillna('').astype('category').cat.codes
tt['night'] = tt['ナイター'].fillna('').astype('category').cat.codes
nm = tt['レース名'].fillna('')
tt['rname'] = np.select([nm.str.contains('優勝'), nm.str.contains('準優'), nm.str.contains('選抜|特選|ドリーム|特別'), nm.str.contains('予選')], [4, 3, 2, 1], 0)
x = V.merge(tt[['day', 'jcd', 'R', 'hour', 'nichi', 'grade', 'night', 'rname']], on=['day', 'jcd', 'R'], how='left')
x['dow'] = pd.to_datetime(x.day).dt.dayofweek; x['lf'] = np.log(x.final)
C = pd.read_pickle(SP + 'cards6.pkl')
c1 = C[C.b == 1][['day', 'jcd', 'R', 'nat', 'cls']].rename(columns={'nat': 'nat1', 'cls': 'cls1'}); c1['day'] = c1.day.astype(str)
cm = C.groupby(['day', 'jcd', 'R']).agg(natmax=('nat', 'max'), nA1=('cls', lambda s: (s == 'A1').sum())).reset_index(); cm['day'] = cm.day.astype(str)
x = x.merge(c1, on=['day', 'jcd', 'R'], how='left').merge(cm, on=['day', 'jcd', 'R'], how='left')
x['a1_1'] = (x.cls1 == 'A1').astype(int); x['natgap'] = x.nat1 - x.natmax
x = x.sort_values(['day', 'jcd', 'R']).reset_index(drop=True)
days = sorted(x.day.unique())
# 過去4週の同場同R・同場の中央値（その日より前だけ）
hist = {}
for i, d in enumerate(days):
    past = x[(x.day < d) & (x.day >= days[max(0, i - 28)])]
    hist[d] = (past.groupby(['jcd', 'R']).lf.median(), past.groupby('jcd').lf.median())
x['h_jr'] = [hist[d][0].get((j, r), np.nan) for d, j, r in zip(x.day, x.jcd, x.R)]
x['h_j'] = [hist[d][1].get(j, np.nan) for d, j in zip(x.day, x.jcd)]
# 当日の売れ行き：同場の前Rの票数、前Rまでの「過去比」の平均
x['res'] = x.lf - x.h_jr
g = x.groupby(['day', 'jcd'])
x['prev_lf'] = g.lf.shift(1)
x['prev_res'] = g.res.shift(1)
x['day_res'] = g.res.transform(lambda s: s.shift(1).expanding().mean())
# 当日・同時刻の他場の売れ行き（前Rまでの全場平均）は省略
F = ['jcd', 'R', 'dow', 'hour', 'nichi', 'grade', 'night', 'rname', 'h_jr', 'h_j', 'prev_lf', 'prev_res', 'day_res', 'nat1', 'a1_1', 'natmax', 'nA1', 'natgap']
x = x[x.day >= days[14]].copy()
x['pred_base'] = x.h_jr
x['pred'] = np.nan
for d in x.day.unique():
    tr = x.day != d
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=30).fit(x.loc[tr, F], x.lf[tr])
    x.loc[~tr, 'pred'] = m.predict(x.loc[~tr, F])
for c, l in [('pred_base', '過去4週の中央値'), ('pred', '新モデル')]:
    e = np.abs(x[c] - x.lf); e = e[x[c].notna()]
    print(f'{l:12s} ±25%以内 {(e < np.log(1.25)).mean()*100:3.0f}%  ±50%以内 {(e < np.log(1.5)).mean()*100:3.0f}%  誤差の中央値 {(np.exp(e.median())-1)*100:.0f}%')
e = np.abs(x.pred - x.lf)
print('R別 ±25%以内（1Rは前Rがないので弱い）:', ' '.join(f'{r}R:{(e[x.R==r] < np.log(1.25)).mean()*100:.0f}%' for r in range(1, 13)))
m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=30).fit(x[F], x.lf)
from sklearn.inspection import permutation_importance
s = x.sample(5000, random_state=0); pi = permutation_importance(m, s[F], s.lf, n_repeats=3, random_state=0)
print('効いてる特徴:', ', '.join(f'{F[i]}={pi.importances_mean[i]:.3f}' for i in np.argsort(-pi.importances_mean)[:10]))
x[['day', 'jcd', 'R', 'final', 'pred']].assign(pred=lambda d: np.exp(d.pred)).to_pickle(SP + 'pool_pred.pkl')
