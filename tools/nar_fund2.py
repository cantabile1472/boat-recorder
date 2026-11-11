# 地方競馬：ベンター方式の自前モデル用の特徴（第2版）
#  能力指数（基準タイム・馬場差・斤量補正・クラス別）、騎手/調教師の直近成績、脚質とペース、クラス変化、当日の傾向
#  python tools/nar_fund2.py → scratchpad/nar_fund2.pkl
import gzip, json, glob, re, datetime
import numpy as np, pandas as pd
SP = '/tmp/claude-0/-home-claude/2ac40992-b703-5112-9a19-f709de764321/scratchpad/'
BC = {'3': '帯広ば', '10': '盛岡', '11': '水沢', '18': '浦和', '19': '船橋', '20': '大井', '21': '川崎', '22': '金沢', '23': '笠松', '24': '名古屋', '27': '園田', '28': '姫路', '31': '高知', '32': '佐賀', '36': '門別'}
TRK = {'良': 0, '稍重': 1, '重': 2, '不良': 3}


def tsec(t):
    m = re.match(r'(\d+):(\d+\.\d)', str(t or ''))
    return int(m.group(1)) * 60 + float(m.group(2)) if m else np.nan


def first_pos(c):
    try:
        return int(str(c).split('-')[0])
    except Exception:
        return np.nan


rows = []
for f in sorted(glob.glob('data/nar/cards_*.jsonl.gz')):
    for l in gzip.open(f, 'rt', encoding='utf-8'):
        d = json.loads(l)
        if d.get('bc') != '3':
            rows.append(d)
C = pd.DataFrame(rows); C['place'] = C.bc.map(BC); C['date'] = pd.to_datetime(C.day)
C['key'] = C.place + '_' + C.day + '_' + C.R.astype(str)
C['t'] = C.time.map(tsec); C['trk'] = C.track.map(TRK); C['fin'] = pd.to_numeric(C.fin_txt, errors='coerce')
C['nh'] = C.groupby('key').num.transform('count')
C = C.sort_values(['date', 'place', 'R', 'num']).reset_index(drop=True)
print('出馬表', len(C), '頭', C.key.nunique(), 'R', C.day.min(), '〜', C.day.max())

# ---- 基準タイム（競馬場×距離×馬場、1〜5着）と、格（賞金帯）での補正、日ごとの馬場差
C['pz'] = pd.cut(np.log10(C.prize1.clip(1e5, 1e8)), [5, 5.7, 6.0, 6.3, 6.6, 8], labels=False)
base = C[(C.fin <= 5) & C.t.notna()]
STD = base.groupby(['place', 'dist', 'trk']).t.median(); STD2 = base.groupby(['place', 'dist']).t.median()
def std(p, d, k):
    try:
        return STD.loc[(p, d, k)]
    except KeyError:
        return STD2.get((p, d), np.nan)
C['std'] = [std(p, d, k) for p, d, k in zip(C.place, C.dist, C.trk)]
C['dev'] = (C.t - C['std']) / C.dist * 1000
VAR = C[C.fin <= 5].groupby(['place', 'day']).dev.median()
CLS = (C[C.fin <= 3].assign(v=lambda x: x.dev - [VAR.get((p, d), 0) for p, d in zip(x.place, x.day)]).groupby('pz').v.median())
print('格ごとの基準（1,000mあたり秒、小さいほど速い）', CLS.round(2).to_dict())

def si(place, day, dist, trk, t, wt):
    s = std(place, dist, trk)
    if not (s == s) or not (t == t):
        return np.nan
    v = VAR.get((place, day), 0.0); v = 0.0 if v != v else v
    w = 0.0 if (wt is None or not (wt == wt)) else (float(wt) - 55) * 0.05   # 斤量1kg ≒ 1,000mあたり0.05秒
    return -((t - s) / dist * 1000 - v) + w

# ---- 騎手・調教師の直近60日成績（その日より前だけ）
C['win'] = (C.fin == 1).astype(int); C['in3'] = (C.fin <= 3).astype(int)
def rolling_rate(col):
    out = np.full(len(C), np.nan); out3 = np.full(len(C), np.nan); cnt = np.zeros(len(C))
    for name, g in C.groupby(col):
        dts = g.date.values; w = g.win.values; t3 = g.in3.values; idx = g.index.values
        cw = np.concatenate([[0], np.cumsum(w)]); c3 = np.concatenate([[0], np.cumsum(t3)])
        lo = np.searchsorted(dts, dts - np.timedelta64(60, 'D')); hi = np.searchsorted(dts, dts)   # その日より前
        n = hi - lo
        out[idx] = np.where(n > 0, (cw[hi] - cw[lo]) / np.maximum(n, 1), np.nan); out3[idx] = np.where(n > 0, (c3[hi] - c3[lo]) / np.maximum(n, 1), np.nan); cnt[idx] = n
    return out, out3, cnt
C['j_win'], C['j_in3'], C['j_n'] = rolling_rate('jockey')
C['t_win'], C['t_in3'], C['t_n'] = rolling_rate('trainer')

# ---- 過去走から：能力指数・脚質・クラス変化
feat = []
for r in C.itertuples():
    ps = [p for p in (r.past or []) if p]
    sis, fpos, l3, fins = [], [], [], []
    for p in ps:
        try:
            dd = datetime.datetime.strptime(p['date'], '%y.%m.%d').strftime('%Y%m%d')
        except Exception:
            dd = ''
        sis.append(si(p.get('place'), dd, p.get('dist'), TRK.get(p.get('track')), tsec(p.get('time')), p.get('wt')))
        fp = first_pos(p.get('corner')); nh = p.get('nh') or np.nan
        fpos.append(fp / nh if fp == fp and nh == nh and nh else np.nan); l3.append(p.get('last3f') or np.nan)
        fins.append(p.get('fin') if isinstance(p.get('fin'), int) else np.nan)
    s3 = [v for v in sis[:3] if v == v]; s5 = [v for v in sis[:5] if v == v]
    p0 = ps[0] if ps else {}
    try:
        days = (r.date - datetime.datetime.strptime(p0['date'], '%y.%m.%d')).days
    except Exception:
        days = np.nan
    feat.append(dict(si_last=sis[0] if sis else np.nan, si_best3=max(s3) if s3 else np.nan, si_mean3=np.mean(s3) if s3 else np.nan,
                     si_best5=max(s5) if s5 else np.nan, si_trend=(s3[0] - np.mean(s3[1:])) if len(s3) >= 2 else np.nan,
                     front=np.nanmean(fpos[:3]) if any(v == v for v in fpos[:3]) else np.nan, l3_mean=np.nanmean(l3[:3]) if any(v == v for v in l3[:3]) else np.nan,
                     fin_last=fins[0] if fins else np.nan, pop_last=p0.get('pop') or np.nan, days=days, npast=len(ps),
                     j_change=int(bool(p0) and bool(p0.get('jockey')) and not str(r.jockey).startswith(str(p0.get('jockey'))[:2])),
                     transfer=int(bool(p0) and p0.get('place') not in (None, r.place)), dist_change=(r.dist - p0.get('dist', r.dist)) if p0 else 0))
F = pd.concat([C.reset_index(drop=True), pd.DataFrame(feat)], axis=1)
g = F.groupby('key')
for c in ['si_last', 'si_best3', 'si_mean3', 'si_best5', 'front', 'l3_mean', 'j_win', 't_win']:
    F[c + '_d'] = F[c] - g[c].transform('mean'); F[c + '_rk'] = g[c].rank(ascending=False if c not in ('front', 'l3_mean') else True)
F['n_front'] = g.front.transform(lambda s: (s < 0.3).sum())            # 先行しそうな馬の数（ペース）
F['wt_d'] = F.wt - g.wt.transform('mean'); F['waku_r'] = F.waku / F.nh.clip(1)
F['here_win'] = [r[0] / max(sum(r), 1) if isinstance(r, list) and sum(r) else np.nan for r in F.rec_here]
F['all_win'] = [r[0] / max(sum(r), 1) if isinstance(r, list) and sum(r) else np.nan for r in F.rec_all]
# ---- 当日の傾向（同じ日・同じ場の、それより前のレース）：内枠・先行の勝ち具合
F['w_in'] = (F.waku_r <= 0.4).astype(float); F['w_front'] = (F.front < 0.3).astype(float)
day_rows = []
for (pl, dy), t in F.groupby(['place', 'day']):
    t = t.sort_values('R'); res = {}
    for R_, u in t.groupby('R'):
        prev = t[t.R < R_]; wn = prev[prev.fin == 1]
        res[R_] = (wn.w_in.mean() if len(wn) else np.nan, wn.w_front.mean() if len(wn) else np.nan, len(wn))
    for R_, (a, b, n) in res.items():
        day_rows.append((pl, dy, R_, a, b, n))
D = pd.DataFrame(day_rows, columns=['place', 'day', 'R', 'day_in', 'day_front', 'day_n'])
F = F.merge(D, on=['place', 'day', 'R'], how='left')
F['bias_in'] = F.day_in * F.w_in; F['bias_front'] = F.day_front * F.w_front
F['sexn'] = F.sex.map({'牡': 0, '牝': 1, 'セ': 2})
F.drop(columns=['past']).to_pickle(SP + 'nar_fund2.pkl'); print('保存', len(F))
