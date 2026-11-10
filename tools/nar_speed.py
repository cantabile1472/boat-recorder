# 地方競馬：走破タイムから能力指数を作り、出走表の特徴と合わせた1頭1行の表にする
#  python tools/nar_speed.py → scratchpad/nar_fund.pkl
import gzip, json, glob, re, datetime
import numpy as np, pandas as pd
SP = '/tmp/claude-0/-home-claude/2ac40992-b703-5112-9a19-f709de764321/scratchpad/'
BC = {'3': '帯広ば', '10': '盛岡', '11': '水沢', '18': '浦和', '19': '船橋', '20': '大井', '21': '川崎', '22': '金沢', '23': '笠松', '24': '名古屋', '27': '園田', '28': '姫路', '31': '高知', '32': '佐賀', '36': '門別'}
TRK = {'良': 0, '稍重': 1, '重': 2, '不良': 3}


def tsec(t):
    m = re.match(r'(\d+):(\d+\.\d)', str(t or ''))
    return int(m.group(1)) * 60 + float(m.group(2)) if m else np.nan


rows = []
for f in sorted(glob.glob('data/nar/cards_*.jsonl.gz')):
    for l in gzip.open(f, 'rt', encoding='utf-8'):
        d = json.loads(l)
        if d.get('bc') == '3':
            continue
        rows.append(d)
C = pd.DataFrame(rows); print('出走表', len(C), '頭')
C['place'] = C.bc.map(BC); C['date'] = pd.to_datetime(C.day)
C['t'] = C.time.map(tsec); C['trk'] = C.track.map(TRK)
C['fin'] = pd.to_numeric(C.fin_txt, errors='coerce')
# ---- 基準タイム（3〜7月の結果から）：競馬場×距離×馬場の中央値（1着〜5着の馬のみ）
base = C[(C.day < '20260801') & (C.fin <= 5) & C.t.notna()]
STD = base.groupby(['place', 'dist', 'trk']).t.median()
STD_pd = base.groupby(['place', 'dist']).t.median()


def std_time(place, dist, trk):
    try:
        return STD.loc[(place, dist, trk)]
    except KeyError:
        try:
            return STD_pd.loc[(place, dist)]
        except KeyError:
            return np.nan


# ---- 日ごとの馬場の速さ（その日その競馬場の、基準とのズレの中央値。1,000mあたり秒）
C['std'] = [std_time(p, d, k) for p, d, k in zip(C.place, C.dist, C.trk)]
C['dev'] = (C.t - C['std']) / C.dist * 1000
VAR = C[C.fin <= 5].groupby(['place', 'day']).dev.median()


def si(place, date, dist, trk, t, margin):
    """能力指数：基準タイムより1,000mあたり何秒速いか（馬場の速さを補正）。大きいほど強い"""
    s = std_time(place, dist, trk)
    if not (s == s) or not (t == t):
        return np.nan
    v = VAR.get((place, date), 0.0)
    return -((t - s) / dist * 1000 - (v if v == v else 0.0))


out = []
for r in C.itertuples():
    ps = [p for p in (r.past or []) if p]
    sis, fins, pops, gaps, l3 = [], [], [], [], []
    for p in ps:
        try:
            dd = datetime.datetime.strptime(p['date'], '%y.%m.%d').strftime('%Y%m%d')
        except Exception:
            dd = ''
        sis.append(si(p.get('place'), dd, p.get('dist'), TRK.get(p.get('track')), tsec(p.get('time')), p.get('margin')))
        fins.append(p.get('fin') if isinstance(p.get('fin'), int) else np.nan); pops.append(p.get('pop') or np.nan)
    p0 = ps[0] if ps else {}
    try:
        days = (r.date - datetime.datetime.strptime(p0['date'], '%y.%m.%d')).days
    except Exception:
        days = np.nan
    s3 = [v for v in sis[:3] if v == v]
    out.append(dict(place=r.place, day=r.day, R=r.R, num=r.num, nh=None, dist=r.dist, trk=r.trk, age=r.age, sex=r.sex, wt=r.wt, hw=r.hw, hw_diff=r.hw_diff,
                    si_last=sis[0] if sis else np.nan, si_best3=max(s3) if s3 else np.nan, si_mean3=np.mean(s3) if s3 else np.nan, si_n=len(s3),
                    fin_last=fins[0] if fins else np.nan, fin_mean=np.nanmean(fins) if fins and np.isfinite(fins).any() else np.nan, pop_last=pops[0] if pops else np.nan,
                    days=days, npast=len(ps), j_change=int(bool(p0) and p0.get('jockey', '') != '' and p0.get('jockey') != r.jockey[:len(p0.get('jockey', ''))]),
                    transfer=int(bool(p0) and p0.get('place') not in (None, r.place)), dist_change=(r.dist - p0.get('dist', r.dist)) if p0 else 0,
                    l3_last=p0.get('last3f', np.nan) if p0 else np.nan, jockey=r.jockey, rec_all=r.rec_all))
F = pd.DataFrame(out)
F['key'] = F.place + '_' + F.day + '_' + F.R.astype(str)
g = F.groupby('key')
for c in ['si_last', 'si_best3', 'si_mean3']:
    F[c + '_d'] = F[c] - g[c].transform('mean')                         # レース内での相対値
    F[c + '_rk'] = g[c].rank(ascending=False)
F['wt_d'] = F.wt - g.wt.transform('mean')
F.to_pickle(SP + 'nar_fund.pkl')
print('能力指数あり', F.si_best3.notna().mean().round(3), '件数', len(F))
