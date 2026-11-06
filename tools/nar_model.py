# 自前モデル：出馬表だけ（オッズなし）で勝率を出す。学習は nar_all.pkl（2026/3〜10）
#  使い方: python tools/nar_model.py train            → model を保存、10月での精度を表示
#          python tools/nar_model.py predict deba.html 頭数 → 馬ごとの勝率
import sys, os, re, pickle, datetime
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nar_cards
SP = '/tmp/claude-0/-home-claude/2ac40992-b703-5112-9a19-f709de764321/scratchpad/cl/'
MP = os.path.join(SP, 'nar_model.pkl')
FEATS = ['nh', 'rec_n', 'rec_win', 'rec_in3', 'here_n', 'here_in3', 'dist_n', 'dist_in3', 'npast', 'p1_fin', 'p1_pop', 'p1_nh', 'p1_margin',
         'p1_rel', 'past_mean_fin', 'past_wins', 'past_in3', 'past_mean_pop', 'p1_same', 'days', 'jk_win', 'jk_n', 'age']


def rec(v):
    v = v if isinstance(v, (list, tuple)) and len(v) == 4 else [0, 0, 0, 0]
    n = sum(v)
    return n, (v[0] / n if n else np.nan), ((v[0] + v[1] + v[2]) / n if n else np.nan)


def feats_from_row(r, day):
    """学習データ（nar_all の1行）→ 特徴"""
    n, w, i3 = rec(r['rec_all']); hn, _, hi3 = rec(r['rec_here']); dn, _, di3 = rec(r['rec_dist'])
    try:
        d1 = datetime.datetime.strptime('20' + r['p1_date'], '%Y.%m.%d'); days = (datetime.datetime.strptime(str(day), '%Y%m%d') - d1).days
    except Exception:
        days = np.nan
    pf, pn = r['p1_fin'], r['p1_nh']
    return dict(nh=r['頭数'], rec_n=n, rec_win=w, rec_in3=i3, here_n=hn, here_in3=hi3, dist_n=dn, dist_in3=di3, npast=r['npast'],
                p1_fin=pf, p1_pop=r['p1_pop'], p1_nh=pn, p1_margin=r['p1_margin'], p1_rel=(pf / pn if pf and pn else np.nan),
                past_mean_fin=r['past_mean_fin'], past_wins=r['past_wins'], past_in3=r['past_in3'], past_mean_pop=r['past_mean_pop'],
                p1_same=float(bool(r['p1_same_place'])), days=days, age=r['age'])


def feats_from_deba(d, nh, place, day, jk):
    """出馬表（parse_deba の1頭ぶん）→ 特徴"""
    past = [p for p in d.get('past', []) if p]
    n, w, i3 = rec(d.get('rec_all')); hn, _, hi3 = rec(d.get('rec_here')); dn, _, di3 = rec(d.get('rec_dist'))
    p1 = past[0] if past else {}
    fin = [p['fin'] for p in past if isinstance(p.get('fin'), int)]
    pops = [p['pop'] for p in past if p.get('pop')]
    try:
        days = (day - datetime.datetime.strptime('20' + p1['date'], '%Y.%m.%d')).days
    except Exception:
        days = np.nan
    pf = p1.get('fin') if isinstance(p1.get('fin'), int) else np.nan; pn = p1.get('nh', np.nan)
    try:
        age = day.year - (2000 + int(d['birth'][:2]))
    except Exception:
        age = np.nan
    return dict(nh=nh, rec_n=n, rec_win=w, rec_in3=i3, here_n=hn, here_in3=hi3, dist_n=dn, dist_in3=di3, npast=len(past),
                p1_fin=pf, p1_pop=p1.get('pop', np.nan), p1_nh=pn, p1_margin=p1.get('margin', np.nan), p1_rel=(pf / pn if pf == pf and pn else np.nan),
                past_mean_fin=(np.mean(fin) if fin else np.nan), past_wins=sum(1 for f in fin if f == 1), past_in3=sum(1 for f in fin if f <= 3),
                past_mean_pop=(np.mean(pops) if pops else np.nan), p1_same=float(p1.get('place') == place), days=days, age=age, jockey=jk)


def jockey_table(df):
    g = df.groupby('jockey')['win'].agg(['sum', 'count'])
    return {k: ((s + 1) / (c + 10), c) for k, (s, c) in g.iterrows()}   # 平滑化した騎手勝率


def add_jk(F, JK):
    F['jk_win'] = [JK.get(j, (0.1, 0))[0] for j in F['jockey']]
    F['jk_n'] = [JK.get(j, (0.1, 0))[1] for j in F['jockey']]
    return F


def norm(df, p):
    """レース内で勝率の合計が1になるように"""
    return p / df.groupby(['day', 'bc', 'R'])[p.name].transform('sum') if hasattr(p, 'name') else p


if __name__ == '__main__':
    from sklearn.ensemble import HistGradientBoostingClassifier
    if sys.argv[1] == 'train':
        df = pd.read_pickle(SP + 'nar_all.pkl')
        df = df[df['場'] != '帯広'].copy()
        tr = df[df['day'] < '20261001']; te = df[df['day'] >= '20261001']
        JK = jockey_table(tr)
        X = pd.DataFrame([feats_from_row(r, r['day']) for _, r in df.iterrows()], index=df.index); X['jockey'] = df['jockey'].values; X = add_jk(X, JK)
        m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=50)
        m.fit(X.loc[tr.index, FEATS], tr['win'])
        p = pd.Series(m.predict_proba(X.loc[te.index, FEATS])[:, 1], index=te.index, name='pm')
        p = p / p.groupby([te['day'], te['bc'], te['R']]).transform('sum')
        ll = lambda q: -np.mean(te['win'] * np.log(q.clip(1e-6)) + (1 - te['win']) * np.log((1 - q).clip(1e-6)))
        print(f"10月 {len(te)}頭 logloss 自前{ll(p):.4f} 3連単換算{ll(te['pw']):.4f} 単勝換算{ll(te['q_tan']):.4f} 半々{ll((p+te['pw'])/2):.4f}")
        top = te.assign(pm=p).groupby(['day', 'bc', 'R']).apply(lambda g: g.loc[g['pm'].idxmax(), 'win']).mean()
        top2 = te.groupby(['day', 'bc', 'R']).apply(lambda g: g.loc[g['pw'].idxmax(), 'win']).mean()
        print(f"自前の1番人気が勝つ率 {top*100:.1f}%  市場の1番人気 {top2*100:.1f}%")
        JK = jockey_table(df)
        m.fit(X[FEATS], df['win'])
        pickle.dump((m, JK), open(MP, 'wb')); print('保存', MP)
    else:
        m, JK = pickle.load(open(MP, 'rb'))
        h = open(sys.argv[2], encoding='utf-8', errors='replace').read(); nh = int(sys.argv[3]); place = sys.argv[4] if len(sys.argv) > 4 else '船橋'
        d = nar_cards.parse_deba(h); day = datetime.datetime.now()
        # 騎手名：馬番ブロックの先頭テキスト「馬名 騎手 （所属） オッズ (n人気)」
        jks = {}
        for b in re.split(r'<td rowspan="5" class="horseNum">', h)[1:]:
            mm = re.match(r'\s*(\d+)', b); t = nar_cards.txt(b[:3000])
            j = re.search(r'^\d+\s+\S+\s+(\S+?)\s*（', t)
            if mm and j: jks[int(mm.group(1))] = j.group(1)
        F = pd.DataFrame([feats_from_deba(d[k], nh, place, day, jks.get(k, '')) for k in sorted(d)], index=sorted(d)); F = add_jk(F, JK)
        p = m.predict_proba(F[FEATS])[:, 1]; p = p / p.sum()
        for k, v, j in sorted(zip(F.index, p, F['jockey']), key=lambda x: -x[1]):
            print(f"{k}番 {v*100:.1f}% {j}")
