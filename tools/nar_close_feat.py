# 地方競馬：締切前スナップ（nar_odds.jsonl）から、締切オッズ予想用の表を作る
#  スナップ: 1=発走6分前 2=4分前 3=3分前 4=2分半前（締切の約30秒前） 5=1分前（締切後＝ほぼ最終）
import json, glob, os, datetime
import numpy as np, pandas as pd


def tri_p(tri3):
    """3連単オッズ → 各馬の1着確率"""
    inv = {}
    for k in tri3:
        if len(k) < 2 or '-' not in str(k[0]):
            continue
        try:
            o = float(k[1])
        except Exception:
            continue
        if o > 0:
            a = int(k[0].split('-')[0]); inv[a] = inv.get(a, 0) + 1 / o
    s = sum(inv.values())
    return {a: v / s for a, v in inv.items()} if s else {}


def tan(tf):
    out = {}
    for r in tf:
        try:
            out[int(r[0])] = float(r[1])
        except Exception:
            pass
    return out


def load(day_min=None, day_max=None):
    rows = []
    for f in sorted(glob.glob('data/2026*/nar_odds.jsonl')):
        day = f.split('/')[1]
        if (day_min and day < day_min) or (day_max and day > day_max):
            continue
        for l in open(f, encoding='utf-8'):
            d = json.loads(l)
            if d.get('bc') == '3':      # ばんえいは除く
                continue
            o = tan(d.get('tf') or []); p = tri_p(d.get('tri3') or [])
            for h, v in o.items():
                rows.append(dict(day=day, bc=int(d['bc']), R=int(d['R']), post=d.get('post'), snap=int(d['snap']), time=d.get('time'), num=h, odds=v, p3=p.get(h, np.nan)))
    return pd.DataFrame(rows)


def build(S=4, C=5, day_min=None, day_max=None):
    """S=判定スナップ、C=締切（正解）とみなすスナップ"""
    L = load(day_min, day_max).drop_duplicates(['day', 'bc', 'R', 'num', 'snap'], keep='last')
    W = L.pivot_table(index=['day', 'bc', 'R', 'num'], columns='snap', values=['odds', 'p3'], aggfunc='last')
    W.columns = [f'{a}{b}' for a, b in W.columns]; x = W.reset_index()
    P = L.groupby(['day', 'bc', 'R']).post.first().reset_index(); x = x.merge(P, on=['day', 'bc', 'R'])
    need = [f'odds{S}', f'p3{S}', f'odds{C}']
    if any(c not in x for c in need):
        return None, None
    ok = (x[f'odds{S}'] > 0) & (x[f'odds{C}'] > 0) & (x[f'p3{S}'] > 0)
    x = x[ok].copy()
    x['nh'] = x.groupby(['day', 'bc', 'R']).num.transform('count'); x = x[x.nh >= 5]
    K = ['day', 'bc', 'R']; g = lambda c: x.groupby(K)[c]
    for k in range(1, S + 1):
        if f'odds{k}' not in x:
            continue
        x.loc[~(x[f'odds{k}'] > 0), f'odds{k}'] = np.nan; x.loc[~(x[f'p3{k}'] > 0), f'p3{k}'] = np.nan
        x[f's{k}'] = (1 / x[f'odds{k}']) / g(f'odds{k}').transform(lambda s: (1 / s).sum())
        x[f'q{k}'] = x[f'p3{k}'] / g(f'p3{k}').transform('sum')
    x['s_close'] = (1 / x[f'odds{C}']) / g(f'odds{C}').transform(lambda s: (1 / s).sum())
    x['odds_close'] = x[f'odds{C}']
    x['y'] = np.log(x.s_close / x[f's{S}'])
    x['gap'] = np.log(x[f'q{S}'] / x[f's{S}'])
    for a in range(1, S):
        x[f'ds{a}{S}'] = np.log(x[f's{S}'] / x[f's{a}']); x[f'dq{a}{S}'] = np.log(x[f'q{S}'] / x[f'q{a}'])
    x['ls'] = np.log(x[f's{S}']); x['lq'] = np.log(x[f'q{S}'])
    x['rk_s'] = g(f's{S}').rank(ascending=False); x['rk_gap'] = g('gap').rank(ascending=False)
    x['qmax'] = g(f'q{S}').transform('max'); x['ent'] = -g(f'q{S}').transform(lambda s: (s * np.log(s)).sum())
    x['hour'] = pd.to_numeric(x.post.str[:2], errors='coerce')
    F = ['num', 'nh', 'bc', 'hour', 'ls', 'lq', 'gap', 'rk_s', 'rk_gap', 'qmax', 'ent'] + [c for c in x.columns if c.startswith('ds') or c.startswith('dq')]
    return x, F


BABA = {'帯広ば': 3, '盛岡': 10, '水沢': 11, '浦和': 18, '船橋': 19, '大井': 20, '川崎': 21, '金沢': 22, '笠松': 23, '名古屋': 24, '園田': 27, '姫路': 28, '高知': 31, '佐賀': 32, '門別': 36}


def results():
    """月別データ（data/nar/drz_YYYYMM.csv.gz）の単勝：最終オッズと払戻"""
    out = []
    for f in sorted(glob.glob('data/nar/drz_*.csv.gz')):
        d = pd.read_csv(f); d = d[d['式'] == '単勝']
        d = d.assign(bc=d['場'].map(BABA), day=d['日'].astype(str), R=d.R.astype(int), num=pd.to_numeric(d['組'], errors='coerce'))
        out.append(d[['day', 'bc', 'R', 'num', 'o', 'pay']].rename(columns={'o': 'odds_final', 'pay': 'pay'}))
    return pd.concat(out).dropna(subset=['bc', 'num']).astype({'bc': int, 'num': int})
