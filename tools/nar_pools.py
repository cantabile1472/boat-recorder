# 地方競馬：全券種の確定オッズから各馬の強さを逆算して1頭1行の表にする（ベンター方式の市場確率用）
#  python tools/nar_pools.py  → scratchpad/nar_pools.pkl
import pandas as pd, numpy as np, glob, sys
SP = '/tmp/claude-0/-home-claude/2ac40992-b703-5112-9a19-f709de764321/scratchpad/'
out = []
for f in sorted(glob.glob('data/nar/full_*.csv.gz')):
    d = pd.read_csv(f, dtype={'組': str}); d = d[(d['場'] != '帯広ば') & (d.o > 0)]
    d['key'] = d['場'] + '_' + d['日'].astype(str) + '_' + d.R.astype(str)
    d['inv'] = 1 / d.o
    d['inv_n'] = d.inv / d.groupby(['key', '式']).inv.transform('sum')    # 券種内で正規化した確率
    parts = d['組'].str.split('-', expand=True)
    for i in range(3):
        d[f'h{i}'] = pd.to_numeric(parts[i], errors='coerce') if i in parts else np.nan
    feats = []
    def agg(kind, cols, name):
        t = d[d['式'] == kind]
        s = pd.concat([t[['key', c, 'inv_n']].rename(columns={c: 'num'}) for c in cols]).dropna()
        feats.append(s.groupby(['key', 'num']).inv_n.sum().rename(name))
    agg('単勝', ['h0'], 'tan'); agg('３連単', ['h0'], 'tri_1'); agg('馬単', ['h0'], 'ex_1')
    agg('馬複', ['h0', 'h1'], 'q_2'); agg('ワイド', ['h0', 'h1'], 'w_3'); agg('３連複', ['h0', 'h1', 'h2'], 'trio_3')
    agg('３連単', ['h0', 'h1'], 'tri_2')
    fk = d[d['式'] == '複勝'][['key', 'h0', 'inv_n']].rename(columns={'h0': 'num'}).groupby(['key', 'num']).inv_n.sum().rename('fuku')
    feats.append(fk)
    x = pd.concat(feats, axis=1).reset_index()
    t = d[d['式'] == '単勝'][['key', 'h0', 'o', 'pay', '頭数']].rename(columns={'h0': 'num', 'o': 'tan_odds', '頭数': 'nh'})
    x = x.merge(t, on=['key', 'num'], how='inner'); x['mo'] = int(f.split('_')[-1][:6])
    out.append(x); print(f, len(x), flush=True)
X = pd.concat(out); X['win'] = (X.pay > 0).astype(int)
X = X[X.groupby('key').win.transform('sum') == 1].dropna()
X.to_pickle(SP + 'nar_pools.pkl'); print('合計', len(X), '頭', X.key.nunique(), 'R')
