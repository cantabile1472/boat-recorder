# 締切オッズ予想モデルの過去検証（8分前オッズ→締切オッズ、2026/7/19〜11/4、全艇）
#  手順1: 場・曜日・時間・強さから締切の単勝票数を推定（ボートキャストの票数）
#  手順2〜5: 締切前シェアと3連単換算から締切シェアを予想する式を作り、学習期間で当てはめ、検証期間で精度を測り、改良を繰り返す
import pandas as pd, numpy as np, glob, sys
from scipy.optimize import minimize
SP = '/tmp/claude-0/-home-claude/2ac40992-b703-5112-9a19-f709de764321/scratchpad/cl/'
x = pd.read_pickle(SP + 'win_all.pkl'); x = x[(x.o8 > 0) & (x.oc > 0) & (x.p8 > 0)].copy()
b1 = pd.read_pickle(SP + 'b1_all.pkl')[['day', 'jcd', 'R', 'hour']]
x = x.merge(b1, on=['day', 'jcd', 'R'], how='left')
# 票数（締切）
rows = []
for f in sorted(glob.glob('data/bcvote/2026*.csv.gz')):
    d = pd.read_csv(f); day = int(f.split('/')[-1][:8])
    for r in d.itertuples():
        try:
            seg = str(r.hyousu1).split('|'); v = [int(t) for t in seg[6].split()[:6]]
            rows.append((day, int(r.jo), int(r.R), sum(v), v))
        except Exception:
            pass
V = pd.DataFrame(rows, columns=['day', 'jcd', 'R', 'votes', 'vb'])
x['day'] = x.day.astype(int); x = x.merge(V[['day', 'jcd', 'R', 'votes']], on=['day', 'jcd', 'R'], how='left')
x['dow'] = pd.to_datetime(x.day.astype(str)).dt.dayofweek
# レース単位に整形
R = []
for k, t in x.groupby(['day', 'jcd', 'R']):
    if len(t) != 6:
        continue
    t = t.sort_values('b'); s0 = 1 / t.o8.values; s0 /= s0.sum(); sc = 1 / t.oc.values; sc /= sc.sum(); p = t.p8.values / t.p8.sum()
    R.append(dict(day=k[0], jcd=k[1], R=k[2], hour=t.hour.iloc[0], dow=t.dow.iloc[0], votes=t.votes.iloc[0], s0=s0, sc=sc, p=p, pmax=p.max()))
D = pd.DataFrame(R); print(len(D), 'レース（6艇そろい）', '票数あり', D.votes.notna().sum())
tr = D[D.day < 20261001]; te = D[D.day >= 20261001]
print('学習', len(tr), '検証', len(te))

# ---------- 手順1: 票数の推定 ----------
V2 = D[D.votes.notna()].copy(); V2['lv'] = np.log(V2.votes.clip(1))
V2['jcd_c'] = V2.jcd.astype(int); V2['night'] = (V2.hour >= 16).astype(int); V2['wk'] = (V2.dow >= 5).astype(int); V2['lateR'] = (V2.R >= 9).astype(int)
from sklearn.linear_model import Ridge
X1 = pd.get_dummies(V2[['night', 'wk', 'lateR', 'pmax']].assign(jcd_c=V2.jcd_c.astype(str)), columns=['jcd_c']).astype(float)
trm = (V2.day < 20261001).values
m1 = Ridge(alpha=1.0).fit(X1[trm], V2.lv[trm]); pv = np.exp(m1.predict(X1[~trm]))
print(f"手順1 票数モデル: 検証 中央値絶対誤差 {np.median(np.abs(pv - V2.votes[~trm]) / V2.votes[~trm]) * 100:.0f}%  決定係数{m1.score(X1[trm], V2.lv[trm]):.2f}")
co = dict(zip(X1.columns, m1.coef_)); print('  効き方（対数）: ナイター%+.2f 土日%+.2f 9R以降%+.2f 本命の強さ%+.2f' % (co['night'], co['wk'], co['lateR'], co['pmax']))

# ---------- 手順2〜5: 締切シェアの予想式 ----------
S0 = np.stack(D.s0); SC = np.stack(D.sc); P = np.stack(D.p); TR = (D.day < 20261001).values; TE = ~TR
def evaluate(pred, mask, label):
    po = 0.75 / pred[mask]; oc = 0.75 / SC[mask]; e = np.abs(np.log(po) - np.log(oc))
    print(f"  {label:36s} 全艇±25%以内 {(e < 0.25).mean()*100:.0f}% ±10% {(e < 0.1).mean()*100:.0f}% | 1号艇±25% {(e[:, 0] < 0.25).mean()*100:.0f}% ±10% {(e[:, 0] < 0.1).mean()*100:.0f}% | 誤差{np.mean(e**2):.3f}")
print('--- 検証期間（10〜11月）での精度')
evaluate(S0, TE, 'v0 8分前のまま')
# v1: 強さ比例（λ固定）
def v1(th, S0=S0, P=P):
    lam = th[0]; return (S0 + lam * P) / (1 + lam)
r1 = minimize(lambda th: np.mean((np.log(v1(th)[TR]) - np.log(SC[TR]))**2), [2.0], method='Nelder-Mead'); evaluate(v1(r1.x), TE, f'v1 強さ比例 λ={r1.x[0]:.2f}')
# v2: λ を票数（8分前の薄さ）で変える：票が少ないほど残りが大きい → λ = a * (推定締切票数/今の票数)… 今の票数は不明なので、8分前の本命オッズの歪み（s0とpの差の大きさ）で代用
gap = np.abs(np.log(S0) - np.log(P)).mean(1)
def v2(th):
    lam = np.exp(th[0] + th[1] * gap)[:, None]; return (S0 + lam * P) / (1 + lam)
r2 = minimize(lambda th: np.mean((np.log(v2(th)[TR]) - np.log(SC[TR]))**2), [0.7, 0.5], method='Nelder-Mead'); evaluate(v2(r2.x), TE, f'v2 ズレが大きいほど残り票大 th={np.round(r2.x,2)}')
# v3: 強さの重みを非線形（強い艇にさらに集まる）
def v3(th):
    lam, a = th; w = P**a; w /= w.sum(1, keepdims=True); return (S0 + lam * w) / (1 + lam)
r3 = minimize(lambda th: np.mean((np.log(v3(th)[TR]) - np.log(SC[TR]))**2), [2.0, 1.0], method='Nelder-Mead'); evaluate(v3(r3.x), TE, f'v3 強さ^a λ={r3.x[0]:.2f} a={r3.x[1]:.2f}')
# v4: 3連単換算と単勝換算を混ぜた「真の強さ」を基準に（単勝側にも情報があるなら）
def v4(th):
    lam, a, m = th; q = np.exp(m * np.log(P) + (1 - m) * np.log(S0)); q /= q.sum(1, keepdims=True); w = q**a; w /= w.sum(1, keepdims=True); return (S0 + lam * w) / (1 + lam)
r4 = minimize(lambda th: np.mean((np.log(v4(th)[TR]) - np.log(SC[TR]))**2), [2.0, 1.0, 0.8], method='Nelder-Mead'); evaluate(v4(r4.x), TE, f'v4 3連単{r4.x[2]:.2f}:単勝{1-r4.x[2]:.2f}の混合 λ={r4.x[0]:.2f} a={r4.x[1]:.2f}')
# v5: v4 + λを時間帯・ナイター・R で変える
hour = D.hour.fillna(12).values; night = (hour >= 16).astype(float); lateR = (D.R.values >= 9).astype(float); wk = (D.dow.values >= 5).astype(float)
def v5(th):
    l0, a, m, b1_, b2_, b3_, b4_ = th; lam = np.exp(l0 + b1_ * night + b2_ * lateR + b3_ * wk + b4_ * gap)[:, None]
    q = np.exp(m * np.log(P) + (1 - m) * np.log(S0)); q /= q.sum(1, keepdims=True); w = q**a; w /= w.sum(1, keepdims=True); return (S0 + lam * w) / (1 + lam)
r5 = minimize(lambda th: np.mean((np.log(v5(th)[TR]) - np.log(SC[TR]))**2), [0.7, 1.0, 0.8, 0, 0, 0, 0.3], method='Nelder-Mead', options={'maxiter': 4000}); evaluate(v5(r5.x), TE, f'v5 +時間帯/R/土日/ズレでλ可変 th={np.round(r5.x,2)}')
print('--- 参考：学習期間での精度（過学習チェック）'); evaluate(v5(r5.x), TR, 'v5 学習期間')
np.save(SP + 'close_model_v5.npy', r5.x)
# 残差の構造：どういうレースで外れるか
pred = v5(r5.x); e1 = np.abs(np.log(0.75 / pred[:, 0]) - np.log(0.75 / SC[:, 0]))
D['err1'] = e1; D['o8_1'] = 0.75 / S0[:, 0]
print('--- 1号艇の誤差（±25%を超える率）: 8分前オッズ帯別')
for lo, hi in [(1, 1.5), (1.5, 2), (2, 3), (3, 5), (5, 99)]:
    s = D[(D.o8_1 >= lo) & (D.o8_1 < hi) & TE]; print(f"  8分前{lo}〜{hi}倍: {len(s)}R 外れ率{(s.err1 >= 0.25).mean()*100:.0f}%")
