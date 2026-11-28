# 戦略Z3（記録のみ）：地方競馬の1番人気（締切1分前の単勝で一番低い馬）の複勝
#  条件：前走より距離が400mを超えて短い（オッズ制限なし）、または 100mを超えて短い かつ 1分前の単勝1.6倍以下
#  使うもの：data/日付/nar_odds.jsonl（snap3＝1分前）、出馬表 data/nar/daily/cards_日付.jsonl.gz（または月別）、複勝の払戻 data/nar_payouts/
#  使い方：python3 tools/z3_eval.py 20261128 → 開始日以降を集計し、data/日付/z3_log.csv を書く
import os, sys, json, gzip, glob, csv, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
f = lambda v: float(v) if re.fullmatch(r'\d+(\.\d+)?', str(v)) else 0.0
def cards(day):
    p = os.path.join(ROOT, 'data', 'nar', 'daily', f'cards_{day}.jsonl.gz')
    src = p if os.path.exists(p) else os.path.join(ROOT, 'data', 'nar', f'cards_{day[:6]}.jsonl.gz')
    C = {}
    if os.path.exists(src):
        for l in gzip.open(src, 'rt', encoding='utf-8'):
            x = json.loads(l)
            if x.get('day') == day: C[(str(int(x['bc'])), int(x['R']), int(x['num']))] = x
    return C
def picks(day):
    p = os.path.join(ROOT, 'data', day, 'nar_odds.jsonl')
    if not os.path.exists(p): return None
    C = cards(day)
    if not C: return None
    out = []
    for l in open(p, encoding='utf-8'):
        d = json.loads(l)
        if d.get('snap') != 3: continue
        tan = {int(r[0]): f(r[1]) for r in d['tf'] if f(r[1]) > 0}
        if not tan: continue
        fav = min(tan, key=tan.get); o = tan[fav]; bc = str(int(d['bc'])); R = int(d['R'])
        x = C.get((bc, R, fav))
        if not x: continue
        past = [q for q in x.get('past') or [] if isinstance(q, dict)]
        try: dd = float(x.get('dist')) - float(past[0].get('dist'))
        except Exception: continue
        if dd <= -401 or (dd <= -101 and o <= 1.6):
            out.append((day, bc, R, fav, o, int(dd), x.get('title', '')))
    return out
def fuku(day):
    p = os.path.join(ROOT, 'data', 'nar_payouts', day + '.csv')
    if not os.path.exists(p): return None
    return {(str(int(r['bc'])), int(r['R']), r['combo']): int(r['pay']) for r in csv.DictReader(open(p, encoding='utf-8')) if r['kind'] == '複勝'}, \
           {(str(int(r['bc'])), int(r['R'])) for r in csv.DictReader(open(p, encoding='utf-8'))}
if __name__ == '__main__':
    start = sys.argv[1] if len(sys.argv) > 1 else '20261128'
    n = h = ret = 0; days = 0; miss = []
    for dd in sorted(os.path.basename(x) for x in glob.glob(os.path.join(ROOT, 'data', '2026????'))):
        if dd < start: continue
        P = picks(dd)
        if P is None: miss.append(dd); continue
        F = fuku(dd)
        with open(os.path.join(ROOT, 'data', dd, 'z3_log.csv'), 'w', encoding='utf-8', newline='') as fh:
            w = csv.writer(fh); w.writerow(['day', 'bc', 'R', 'num', 'odds1m', 'dist_change', 'title', 'fuku_pay'])
            for day, bc, R, num, o, dch, t in P:
                pay = '' if F is None else F[0].get((bc, R, str(num)), 0 if (bc, R) in F[1] else '')
                w.writerow([day, bc, R, num, o, dch, t, pay])
                if pay != '': n += 1; ret += pay; h += pay > 0
        days += 1
    print(f'Z3（{start}〜）: {n}点 的中{h} 回収率{ret / n * 100:.1f}%' if n else f'Z3（{start}〜）: まだなし', '／ 出馬表か記録が無い日:', ' '.join(miss) or 'なし')
