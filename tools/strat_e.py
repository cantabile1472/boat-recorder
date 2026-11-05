# 戦略E：複勝・ワイドを「締切1分前のオッズ（下限）」と「3連単オッズから換算した確率」で評価する（全競技共通）
# 期待値 = 確率 × 下限オッズ。締切までにオッズが下がる前提で、割引 d を掛けても th 以上なら買い。
import os, json, time, subprocess, itertools, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEF = {'notify': True, 'd': 0.8, 'th': 1.0, 'lomin': 1.1, 'lomax': 10.0, 'pmin': 0.15,
       'kinds': ['fuku', 'wide'], 'sports': ['kyotei', 'auto', 'nar', 'keirin'], 'max_per_race': 3}
_C = {'t': 0, 'v': None}


def prm():
    """config.json の strategy_E を5分おきに読み直す"""
    if _C['v'] is None or time.time() - _C['t'] > 300:
        _C['t'] = time.time()
        v = None
        if not os.environ.get('NO_GIT'):
            try:
                subprocess.run(['git', 'fetch', '-q', 'origin', 'main'], cwd=ROOT, timeout=60)
                v = json.loads(subprocess.run(['git', 'show', 'origin/main:config.json'], cwd=ROOT,
                                              capture_output=True, text=True, timeout=30).stdout)
            except Exception:
                v = None
        if v is None:
            try:
                v = json.load(open(os.path.join(ROOT, 'config.json'), encoding='utf-8'))
            except Exception:
                v = {}
        d = dict(DEF)
        d.update(v.get('strategy_E', {}))
        d['_table'] = load_table()
        _C['v'] = d
    return _C['v']


def load_table():
    """下がり方の表（data/drop_table.json）。GitHub の最新を読む"""
    t = None
    if not os.environ.get('NO_GIT'):
        try:
            t = json.loads(subprocess.run(['git', 'show', 'origin/main:data/drop_table.json'], cwd=ROOT,
                                          capture_output=True, text=True, timeout=30).stdout)
        except Exception:
            t = None
    if t is None:
        try:
            t = json.load(open(os.path.join(ROOT, 'data', 'drop_table.json'), encoding='utf-8'))
        except Exception:
            t = {}
    return t.get('table', {})


T_LO = [(1, 2), (2, 3), (3, 5), (5, 10), (10, 1e9)]
T_EV = [(0, 0.8), (0.8, 1.0), (1.0, 1.2), (1.2, 1.5), (1.5, 1e9)]


def table_coef(tb, kind, lo, ev, minn=5):
    """表の係数（締切で下限オッズが何割残るか）。件数が少ないマスは None"""
    i = next((n for n, (a, b) in enumerate(T_LO) if a <= lo < b), None)
    k = next((n for n, (a, b) in enumerate(T_EV) if a <= ev < b), None)
    c = tb.get(f'{kind}|{i}|{k}')
    if c and c.get('n', 0) >= minn and c.get('d'):
        return c['d']
    return None


def num(s):
    try:
        return float(str(s).replace(',', '').strip())
    except Exception:
        return 0.0


def probs(tri):
    """tri: {(1着,2着,3着): オッズ} → 各選手の2着内・3着内確率、2頭とも3着内の確率"""
    w = {k: 1 / v for k, v in tri.items() if v and v > 0}
    s = sum(w.values())
    if s <= 0:
        return None
    top2, top3, pair = {}, {}, {}
    for (a, b, c), x in w.items():
        p = x / s
        for e in (a, b):
            top2[e] = top2.get(e, 0) + p
        for e in (a, b, c):
            top3[e] = top3.get(e, 0) + p
        for u, v in itertools.combinations(sorted((a, b, c)), 2):
            pair[(u, v)] = pair.get((u, v), 0) + p
    return top2, top3, pair


def evaluate(fuku, wide, tri, nfuku, P=None):
    """fuku: {選手: (下限, 上限)}  wide: {(小,大): (下限, 上限)}  nfuku: 複勝が何着まで払うか
    戻り値: 全候補のリスト [種別, 買い目, 下限, 上限, 確率, 期待値, 買い]"""
    P = P or prm()
    pr = probs(tri)
    if not pr:
        return []
    top2, top3, pair = pr
    tk = top2 if nfuku == 2 else top3
    out = []
    if 'fuku' in P['kinds']:
        for e, (lo, hi) in fuku.items():
            p = tk.get(e, 0)
            out.append(['複勝', str(e), lo, hi, p, p * lo])
    if 'wide' in P['kinds']:
        for (u, v), (lo, hi) in wide.items():
            p = pair.get((min(u, v), max(u, v)), 0)
            out.append(['ワイド', f'{u}-{v}', lo, hi, p, p * lo])
    for r in out:
        r.append(int(r[2] >= P['lomin'] and r[2] <= P['lomax'] and r[4] >= P['pmin'] and r[5] * P['d'] >= P['th']))
    picks = sorted([r for r in out if r[6]], key=lambda r: -r[5])[:int(P['max_per_race'])]
    keep = {id(r) for r in picks}
    for r in out:
        r[6] = int(id(r) in keep)
    return out


SPORT_OF = {'号艇': 'kyotei', '号車': 'auto', '番': 'nar', '番車': 'keirin'}


def lines(out, unit):
    """通知文。notify_kinds（競技ごとに通知する券種）で絞る。記録は全部残す"""
    P = prm()
    if P.get('notify_mode') == 'table':
        return table_lines(out, unit, P)
    ok = {'fuku': '複勝', 'wide': 'ワイド'}
    ks = (P.get('notify_kinds') or {}).get(SPORT_OF.get(unit, ''), P['kinds'])
    ks = {ok[k] for k in ks if k in ok}
    res = []
    for r in sorted([r for r in out if r[6] and r[0] in ks], key=lambda r: -r[5]):
        tgt = f'{r[1]}{unit}' if r[0] == '複勝' else r[1]
        res.append(f"{r[0]} {tgt}  {r[2]:.1f}〜{r[3]:.1f}倍  確率{r[4]*100:.0f}%  期待値{r[5]:.2f}（{int(P['d']*100)}%に下がっても{r[5]*P['d']:.2f}）")
    return res


def table_lines(out, unit, P):
    """表モード：表のある競技・券種だけ。締切期待値の予想（期待値×係数、係数は上限 table_cap）が table_min 以上なら通知"""
    sp = SPORT_OF.get(unit, '')
    if sp not in P.get('table_sports', ['kyotei']):
        return []
    sr = (P.get('simple_rules') or {}).get(sp)
    if sr:      # 表がまだない競技は簡易ルール（1分前の期待値と下限オッズの範囲だけで判定）
        res = sorted([r for r in out if r[0] in {'fuku': '複勝', 'wide': 'ワイド'}.get(sr.get('kind', 'fuku'), '複勝')
                      and sr.get('lomin', 1.1) <= r[2] < sr.get('lomax', 3) and sr.get('evmin', 0.9) <= r[5] < sr.get('evmax', 99)], key=lambda r: -r[5])
        return [f"{r[0]} {r[1]}{unit if r[0] == '複勝' else ''}  {r[2]:.1f}〜{r[3]:.1f}倍  確率{r[4]*100:.0f}%  期待値{r[5]:.2f}"
                for r in res[:int(P.get('max_per_race', 3))]]
    kinds = {'fuku': '複勝', 'wide': 'ワイド'}
    ks = {kinds[k] for k in P.get('table_kinds', ['fuku'])}
    tb = P.get('_table') or {}
    res = []
    for r in out:
        if r[0] not in ks or r[2] < P.get('lomin', 1.1) or r[2] > P.get('lomax', 10):
            continue
        d = table_coef(tb, r[0], r[2], r[5])
        if d is None:
            continue
        pe = r[5] * min(d, P.get('table_cap', 1.0))
        if pe >= P.get('table_min', 0.7):
            res.append((pe, r))
    res.sort(key=lambda x: -x[0])
    return [f"{r[0]} {r[1]}{unit if r[0] == '複勝' else ''}  {r[2]:.1f}〜{r[3]:.1f}倍  確率{r[4]*100:.0f}%  締切期待値の予想{pe:.2f}"
            for pe, r in res[:int(P.get('max_per_race', 3))]]


def save(ddir, sport, place, R_, dl, out):
    """全候補を e_all.csv、買いだけ e_picks.csv に残す（あとで検証用）"""
    try:
        import datetime
        t = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime('%H:%M:%S')
        for fn, rows in (('e_all.csv', out), ('e_picks.csv', [r for r in out if r[6]])):
            pth = os.path.join(ddir, fn)
            new = not os.path.exists(pth)
            with open(pth, 'a', encoding='utf-8') as f:
                if new:
                    f.write('time,sport,place,R,deadline,kind,sel,lo,hi,p,ev,buy\n')
                for r in rows:
                    f.write(f"{t},{sport},{place},{R_},{dl},{r[0]},{r[1]},{r[2]},{r[3]},{r[4]:.4f},{r[5]:.3f},{r[6]}\n")
    except Exception:
        pass


def notify(title, body):
    tp = os.environ.get('NTFY_TOPIC', '').strip()
    if not tp:
        return
    try:
        rq = urllib.request.Request('https://ntfy.sh/' + tp, data=(title + '\n' + body).encode('utf-8'),
                                    headers={'Priority': 'high'})
        urllib.request.urlopen(rq, timeout=15).read()
    except Exception:
        pass


def rng(s):
    """'2.3-3.1' → (2.3, 3.1)"""
    s = str(s).replace('～', '-').replace('〜', '-')
    a = s.split('-')
    lo = num(a[0]) if a else 0
    hi = num(a[1]) if len(a) > 1 else lo
    return lo, hi


# ---------- 競技ごとの読み取り ----------
def kyotei_parse(tf_pts, k_pts, t3_pts):
    """競艇：oddstf の点（0-5単勝, 6-11複勝）、oddsk の15点（三角形の並び）、odds3t の120点"""
    if len(t3_pts) != 120 or len(tf_pts) < 12 or len(k_pts) < 15:
        return None
    act = [b for b in range(1, 7) if num(tf_pts[b - 1]) > 0]
    fuku = {}
    for b in act:
        lo, hi = rng(tf_pts[5 + b])
        if lo > 0:
            fuku[b] = (lo, hi)
    wide, i = {}, 0
    for b in range(2, 7):
        for a in range(1, b):
            lo, hi = rng(k_pts[i]); i += 1
            if lo > 0 and a in act and b in act:
                wide[(a, b)] = (lo, hi)
    tri = {}
    for i, v in enumerate(t3_pts):
        f = i % 6 + 1
        row = i // 6
        oth = [x for x in range(1, 7) if x != f]
        s = oth[row // 4]
        th = [x for x in oth if x != s][row % 4]
        tri[(f, s, th)] = num(v)
    return fuku, wide, tri, 2


def auto_parse(bd):
    """オート：fnsOddsList / widOddsList / rt3OddsList"""
    tns = bd.get('tnsOddsList') or {}
    act = [int(a) for a, v in tns.items() if num(v) > 0]
    fuku = {}
    for a, v in (bd.get('fnsOddsList') or {}).items():
        lo, hi = num(v.get('min')), num(v.get('max'))
        if lo > 0 and int(a) in act:
            fuku[int(a)] = (lo, hi)
    wide = {}
    for a, d in (bd.get('widOddsList') or {}).items():
        for b, v in (d or {}).items():
            lo, hi = num(v.get('min')), num(v.get('max'))
            if lo > 0 and int(a) in act and int(b) in act:
                wide[(min(int(a), int(b)), max(int(a), int(b)))] = (lo, hi)
    tri = {}
    for a, d1 in (bd.get('rt3OddsList') or {}).items():
        for b, d2 in (d1 or {}).items():
            for c, v in (d2 or {}).items():
                if num(v) > 0:
                    tri[(int(a), int(b), int(c))] = num(v)
    return fuku, wide, tri, (3 if len(act) >= 8 else 2)


def nar_parse(rec):
    """地方競馬：tf は [馬番, 単勝, 複勝下, 複勝上]、wide/tri3 は [組, 下(, 上)]"""
    act = [int(r[0]) for r in rec.get('tf', []) if num(r[1]) > 0]
    fuku = {}
    for r in rec.get('tf', []):
        lo, hi = num(r[2]), num(r[3])
        if lo > 0 and int(r[0]) in act:
            fuku[int(r[0])] = (lo, hi or lo)
    wide = {}
    for r in rec.get('wide', []):
        if '-' not in r[0] or len(r) < 2:
            continue
        a, b = map(int, r[0].split('-'))
        lo = num(r[1]); hi = num(r[2]) if len(r) > 2 else lo
        if lo > 0:
            wide[(min(a, b), max(a, b))] = (lo, hi)
    tri = {}
    for r in rec.get('tri3', []):
        if r[0].count('-') != 2 or len(r) < 2:
            continue
        tri[tuple(map(int, r[0].split('-')))] = num(r[1])
    return fuku, wide, tri, (3 if len(act) >= 8 else 2)
