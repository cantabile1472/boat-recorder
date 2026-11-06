# JRA：結果＋過去5走（YYYYMM.jsonl.gz）と締切オッズ（odds_YYYYMM.jsonl.gz）を結合して馬ごとの表を作る
#  python tools/jra_feat.py  → scratchpad/jra_feat.pkl
import gzip, json, glob, re, datetime, os, sys
import numpy as np, pandas as pd
SP = '/tmp/claude-0/-home-claude/2ac40992-b703-5112-9a19-f709de764321/scratchpad/'
PLACE = {'01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京', '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'}


def num(s):
    try:
        return float(str(s).replace(',', ''))
    except Exception:
        return np.nan


def load_odds():
    O = {}
    for fn in sorted(glob.glob('data/jra/odds_*.jsonl.gz')):
        for l in gzip.open(fn, 'rt', encoding='utf-8'):
            r = json.loads(l); O[r['id']] = r
    return O


def market(o):
    """締切オッズ → 単勝換算・3連単換算の1着率、複勝オッズ、3連単換算の3着内率、馬単換算"""
    out = {}
    tan = {int(k): num(v) for k, v in (o.get('1') or {}).items()}; tan = {k: v for k, v in tan.items() if v > 0}
    S = sum(1 / v for v in tan.values()); q = {k: (1 / v) / S for k, v in tan.items()}
    fuku = {int(k): num(v) for k, v in (o.get('2') or {}).items()}
    t3 = {k: num(v) for k, v in (o.get('8') or {}).items()}; t3 = {k: v for k, v in t3.items() if v > 0}
    inv = {k: 1 / v for k, v in t3.items()}; T = sum(inv.values())
    p1, p3 = {}, {}
    for k, v in inv.items():
        a, b, c = int(k[:2]), int(k[2:4]), int(k[4:])
        p1[a] = p1.get(a, 0) + v
        for h in (a, b, c):
            p3[h] = p3.get(h, 0) + v
    p1 = {k: v / T for k, v in p1.items()} if T else {}; p3 = {k: v / T for k, v in p3.items()} if T else {}
    um = {k: num(v) for k, v in (o.get('6') or {}).items()}; um = {k: v for k, v in um.items() if v > 0}
    U = sum(1 / v for v in um.values()); pu = {}
    for k, v in um.items():
        pu[int(k[:2])] = pu.get(int(k[:2]), 0) + (1 / v) / U
    return tan, q, fuku, p1, p3, pu, t3, um


def build():
    O = load_odds(); rows = []
    for fn in sorted(glob.glob('data/jra/20*.jsonl.gz')):
        if 'odds_' in fn:
            continue
        for l in gzip.open(fn, 'rt', encoding='utf-8'):
            r = json.loads(l); o = O.get(r['id'])
            H = [x for x in r['horses'] if x.get('num')]
            if len(H) < 5:
                continue
            t = r['title'] + r['cond']
            young = bool(re.search(r'(2歳|3歳)', t)) and '以上' not in t
            cls = '新馬' if '新馬' in t else '未勝利' if '未勝利' in t else '1勝' if '1勝' in t else '2勝' if '2勝' in t else '3勝' if '3勝' in t else 'G1' if 'G1' in t or 'GI)' in t else 'G2' if 'G2' in t or 'GII)' in t else 'G3' if 'G3' in t or 'GIII)' in t else 'オープン'
            m = re.search(r'(\d+)R', r['title']); R = int(m.group(1)) if m else None
            m = re.search(r'(\d)回(\S+?)(\d+)日目', r['cond']); kai, dayn = (int(m.group(1)), int(m.group(3))) if m else (None, None)
            nh = len(H)
            tan = q = fuku = p1 = p3 = pu = None
            if o:
                tan, q, fuku, p1, p3, pu, _, _ = market(o)
            o1 = min(num(x['odds']) for x in H if num(x['odds']) > 0) if any(num(x['odds']) > 0 for x in H) else np.nan
            try:
                day = datetime.datetime.strptime(r['day'], '%Y%m%d')
            except Exception:
                continue
            for x in H:
                p = x.get('past') or []; pa = p[0] if p else {}
                fins = [z['fin'] for z in p if isinstance(z.get('fin'), int)]
                pops = [z['pop'] for z in p if z.get('pop')]
                try:
                    days = (day - datetime.datetime.strptime(pa['date'], '%Y.%m.%d')).days
                except Exception:
                    days = np.nan
                sa = re.match(r'(牡|牝|セ)(\d+)', x.get('sexage', '')); fin = x['fin'] if isinstance(x['fin'], int) else np.nan
                n = int(x['num'])
                rows.append(dict(
                    id=r['id'], day=r['day'], year=int(r['day'][:4]), place=PLACE.get(r['id'][4:6], ''), R=R, kai=kai, dayn=dayn, cls=cls, young=young, surf=r['surface'], dist=r['dist'], nh=nh,
                    num=n, fin=fin, win=int(fin == 1), in3=int(fin <= 3) if fin == fin else 0, odds=num(x['odds']), pop=num(x['pop']), o1=o1,
                    sex=sa.group(1) if sa else '', age=int(sa.group(2)) if sa else np.nan, wt=num(x.get('wt')), jockey=x.get('jockey', ''),
                    p1_fin=pa.get('fin', 0) if isinstance(pa.get('fin'), int) else 0, p1_pop=pa.get('pop') or 0, p1_nh=pa.get('nh') or 0, p1_place=pa.get('place', ''), p1_race=pa.get('race', ''),
                    npast=len(p), past_mean_fin=np.mean(fins) if fins else np.nan, past_wins=sum(1 for f in fins if f == 1), past_in3=sum(1 for f in fins if f <= 3), past_mean_pop=np.mean(pops) if pops else np.nan, days=days,
                    tan=(tan or {}).get(n, np.nan), q=(q or {}).get(n, np.nan), fuku=(fuku or {}).get(n, np.nan), pw=(p1 or {}).get(n, np.nan), p3=(p3 or {}).get(n, np.nan), pu=(pu or {}).get(n, np.nan),
                    pay_fuku=0, pay_tan=0))
    d = pd.DataFrame(rows)
    # 払戻（単勝・複勝）を結果ファイルから
    pays = {}
    for fn in sorted(glob.glob('data/jra/20*.jsonl.gz')):
        if 'odds_' in fn:
            continue
        for l in gzip.open(fn, 'rt', encoding='utf-8'):
            r = json.loads(l); pz = r.get('pays', {})
            if '複勝' in pz:
                nums = pz['複勝'][0].split(); ys = pz['複勝'][1].split()
                for a, b in zip(nums, ys):
                    pays[(r['id'], 'f', int(a))] = num(b)
            if '単勝' in pz:   # 同着なら複数
                for a, b in zip(pz['単勝'][0].split(), pz['単勝'][1].split()):
                    pays[(r['id'], 't', int(a))] = num(b)
    d['pay_fuku'] = [pays.get((i, 'f', n), 0) for i, n in zip(d['id'], d['num'])]
    d['pay_tan'] = [pays.get((i, 't', n), 0) for i, n in zip(d['id'], d['num'])]
    d.to_pickle(SP + 'jra_feat.pkl')
    print(len(d), '頭', d['id'].nunique(), 'レース', 'オッズあり', d['pw'].notna().sum())
    return d


def build_pairs():
    """2頭の組：3連単換算の 馬連確率(2頭が1・2着)・ワイド確率(2頭とも3着内) と 馬連・ワイド・馬単オッズ、結果"""
    O = load_odds(); fins = {}
    for fn in sorted(glob.glob('data/jra/20*.jsonl.gz')):
        if 'odds_' in fn:
            continue
        for l in gzip.open(fn, 'rt', encoding='utf-8'):
            r = json.loads(l); fins[r['id']] = (r['day'], {int(x['num']): x['fin'] for x in r['horses'] if x.get('num') and isinstance(x['fin'], int)})
    rows = []
    for rid, o in O.items():
        if rid not in fins:
            continue
        day, fin = fins[rid]
        t3 = {k: num(v) for k, v in (o.get('8') or {}).items()}; t3 = {k: 1 / v for k, v in t3.items() if v > 0}; T = sum(t3.values())
        if T <= 0:
            continue
        pr, pw = {}, {}
        for k, v in t3.items():
            a, b, c = int(k[:2]), int(k[2:4]), int(k[4:])
            key = (min(a, b), max(a, b)); pr[key] = pr.get(key, 0) + v
            for x, y in ((a, b), (a, c), (b, c)):
                kk = (min(x, y), max(x, y)); pw[kk] = pw.get(kk, 0) + v
        ur = {k: num(v) for k, v in (o.get('4') or {}).items()}; wd = {k: num(v) for k, v in (o.get('5') or {}).items()}; ut = {k: num(v) for k, v in (o.get('6') or {}).items()}
        top = sorted(fin, key=lambda h: fin[h])
        for (a, b), v in pr.items():
            k = f"{a:02d}{b:02d}"
            rows.append(dict(id=rid, day=day, year=int(day[:4]), a=a, b=b, p_ren=v / T, p_wide=pw.get((a, b), 0) / T,
                             o_ren=ur.get(k, np.nan), o_wide=wd.get(k, np.nan), o_ut=ut.get(k, np.nan), o_ut_r=ut.get(f"{b:02d}{a:02d}", np.nan),
                             hit_ren=int(len(top) >= 2 and {a, b} == set(top[:2])), hit_wide=int(len(top) >= 3 and a in top[:3] and b in top[:3]),
                             hit_ut=int(len(top) >= 2 and top[0] == a and top[1] == b), hit_ut_r=int(len(top) >= 2 and top[0] == b and top[1] == a)))
    d = pd.DataFrame(rows); d.to_pickle(SP + 'jra_pairs.pkl'); print('組', len(d), d['id'].nunique(), 'レース')
    return d


if __name__ == '__main__':
    build()
    if len(sys.argv) > 1 and sys.argv[1] == 'pairs':
        build_pairs()
