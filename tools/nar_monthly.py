# 地方競馬の月別データ（全券種の締切オッズ＋払戻）をダウンロードして、
# 3連単から計算した確率と各券種のオッズ・払戻をまとめた小さいファイルにする（ドクターZ方式の検証用）
import sys, os, io, zipfile, csv, time, urllib.request, gzip
from collections import defaultdict
Y, M = int(sys.argv[1]), int(sys.argv[2])
B = 'https://www.keiba.go.jp/KeibaWeb/DataDownload/'
def dl(kind):
    u = f'{B}{kind}DataDownload?type=monthly&k_year={Y}&k_month={M}'
    for _ in range(3):
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(rq, timeout=1200) as r: return r.read()
        except Exception as e:
            print('retry', e, flush=True); time.sleep(10)
    return b''
def csvs(blob, key):
    out = []
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
        for n in z.namelist():
            if n.endswith('.csv') and key in n:
                out.append(z.read(n).decode('utf-8-sig', 'replace'))
    except Exception as e:
        print('zip NG', e)
    return out
odds_blob = dl('Odds'); race_blob = dl('Race')
print(Y, M, 'odds', len(odds_blob), 'race', len(race_blob), flush=True)
pays = {}
for t in csvs(race_blob, 'payback'):
    for r in csv.DictReader(io.StringIO(t)):
        k = (r['競馬場'], r['競走年月日'], r['レース番号'])
        def gi(c):
            try: return int(r.get(c, '') or 0)
            except: return 0
        d = {'単勝': {(gi('単勝組番'),): gi('単勝払戻金（円）')},
             '複勝': {(gi(f'複勝組番{i}'),): gi(f'複勝払戻金{i}（円）') for i in (1, 2, 3) if gi(f'複勝組番{i}')},
             '馬複': {tuple(sorted((gi('馬複組番1'), gi('馬複組番2')))): gi('馬複払戻金（円）')},
             '馬単': {(gi('馬単組番1'), gi('馬単組番2')): gi('馬単払戻金（円）')},
             'ワイド': {tuple(sorted((gi(f'ワイド組番{i}馬番1'), gi(f'ワイド組番{i}馬番2')))): gi(f'ワイド払戻金{i}（円）') for i in (1, 2, 3) if gi(f'ワイド組番{i}馬番1')},
             '３連複': {tuple(sorted((gi('３連複組番馬番1'), gi('３連複組番馬番2'), gi('３連複組番馬番3')))): gi('３連複払戻金（円）')}}
        pays[k] = d
races = defaultdict(list)
for t in csvs(odds_blob, 'odds'):
    for r in csv.reader(io.StringIO(t)):
        if not r or r[0] == '競馬場': continue
        races[(r[0], r[1], r[2])].append(r)
os.makedirs('data/nar', exist_ok=True)
fn = f'data/nar/drz_{Y}{M:02d}.csv.gz'
n = 0
with gzip.open(fn, 'wt', encoding='utf-8', newline='') as f:
    w = csv.writer(f); w.writerow(['場', '日', 'R', '頭数', '式', '組', 'o', 'omax', 'p', 'pay'])
    for k, rows in races.items():
        if k not in pays: continue
        q = {}
        for r in rows:
            if r[3] == '３連単':
                try:
                    o = float(r[7])
                    if o > 0: q[(int(r[4]), int(r[5]), int(r[6]))] = 1 / o
                except: pass
        s = sum(q.values())
        if s == 0: continue
        horses = {h for c in q for h in c}; nh = len(horses)
        P = defaultdict(float)
        for (a, b, c), x in q.items():
            x /= s
            P[('単勝', (a,))] += x
            for h in ((a, b) if nh <= 7 else (a, b, c)): P[('複勝', (h,))] += x
            P[('馬複', tuple(sorted((a, b))))] += x; P[('馬単', (a, b))] += x
            for pr in ((a, b), (a, c), (b, c)): P[('ワイド', tuple(sorted(pr)))] += x
            P[('３連複', tuple(sorted((a, b, c))))] += x
        for r in rows:
            kind = r[3]
            if kind not in ('単勝', '複勝', '馬複', '馬単', 'ワイド', '３連複'): continue
            try:
                nums = tuple(int(v) for v in r[4:7] if v)
                o = float(r[7]); om = float(r[8]) if r[8] else ''
            except: continue
            key = nums if kind in ('単勝', '複勝', '馬単') else tuple(sorted(nums))
            p = P.get((kind, key), 0)
            if o <= 0 or p <= 0 or p * o < 0.7 or o > 100: continue
            pay = pays[k].get(kind, {}).get(key, 0)
            w.writerow([k[0], k[1], k[2], nh, kind, '-'.join(map(str, nums)), o, om, round(p, 5), pay]); n += 1
print(fn, n, '行')
