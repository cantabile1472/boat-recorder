# 戦略Z2（記録のみ）の集計：nar_odds.jsonl（4分前=snap1, 1分前=snap3）と nar_payouts の単勝払戻から計算
import os, sys, json, glob, math, csv, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
f = lambda v: float(v) if re.fullmatch(r'\d+(\.\d+)?', str(v)) else 0.0
def picks(day):
    p = os.path.join(ROOT, 'data', day, 'nar_odds.jsonl'); S = {}
    if not os.path.exists(p): return []
    for l in open(p, encoding='utf-8'):
        d = json.loads(l)
        if d.get('snap') in (1, 3): S[(d['bc'], d['R'], d['snap'])] = {r[0]: f(r[1]) for r in d['tf']}
    out = []
    for (bc, R, s), o3 in S.items():
        if s != 3 or (bc, R, 1) not in S: continue
        o1 = S[(bc, R, 1)]
        for n, b in o3.items():
            a = o1.get(n, 0)
            if a > 0 and 6 <= b <= 60 and math.log(b / a) <= -0.3: out.append((bc, int(R), n, a, b))
    return out
def pays(day):
    p = os.path.join(ROOT, 'data', 'nar_payouts', day + '.csv')
    if not os.path.exists(p): return None
    P = {}
    for r in csv.DictReader(open(p, encoding='utf-8')):
        if r['kind'] in ('単勝', 'tan'): P[(str(int(r['bc'])), int(r['R']), str(int(r['combo'])))] = int(r['pay'])
    return P
start = sys.argv[1] if len(sys.argv) > 1 else '20261127'
n = h = ret = 0
for d in sorted(os.path.basename(x) for x in glob.glob(os.path.join(ROOT, 'data', '2026????'))):
    if d < start: continue
    P = pays(d)
    if P is None: continue
    races = {(k[0], k[1]) for k in P}
    for bc, R, num, a, b in picks(d):
        if (str(int(bc)), R) not in races: continue
        pay = P.get((str(int(bc)), R, num), 0); n += 1; ret += pay; h += pay > 0
print(f'Z2（{start}〜）: {n}点 的中{h} 回収率{ret / n:.0f}%' if n else f'Z2（{start}〜）: まだなし')
