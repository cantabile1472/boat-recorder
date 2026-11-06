# 地方競馬の月別データ（公式ダウンロード）から、締切オッズ全券種・全組（3連単含む）と払戻を「間引きなし」で保存する（手順1）
#  data/nar/full_YYYYMM.csv.gz : 組ごと1行（場,日,R,頭数,式,組,o,omax,p,pay）
#  data/nar/prob_YYYYMM.csv.gz : 馬ごと1行（場,日,R,頭数,馬番,pw,p2,p3,tan,fuku_lo,fuku_hi,fin）
import sys, os, io, zipfile, csv, time, urllib.request, gzip
from collections import defaultdict
Y, M = int(sys.argv[1]), int(sys.argv[2])
B = 'https://www.keiba.go.jp/KeibaWeb/DataDownload/'


def dl(kind):
    u = f'{B}{kind}DataDownload?type=monthly&k_year={Y}&k_month={M}'
    for _ in range(3):
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(rq, timeout=1200) as r:
                return r.read()
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
pays = {}; fins = {}
for t in csvs(race_blob, 'payback'):
    for r in csv.DictReader(io.StringIO(t)):
        k = (r['競馬場'], r['競走年月日'], r['レース番号'])

        def gi(c):
            try:
                return int(r.get(c, '') or 0)
            except Exception:
                return 0
        d = {'単勝': {(gi('単勝組番'),): gi('単勝払戻金（円）')},
             '複勝': {(gi(f'複勝組番{i}'),): gi(f'複勝払戻金{i}（円）') for i in (1, 2, 3) if gi(f'複勝組番{i}')},
             '馬複': {tuple(sorted((gi('馬複組番1'), gi('馬複組番2')))): gi('馬複払戻金（円）')},
             '馬単': {(gi('馬単組番1'), gi('馬単組番2')): gi('馬単払戻金（円）')},
             'ワイド': {tuple(sorted((gi(f'ワイド組番{i}馬番1'), gi(f'ワイド組番{i}馬番2')))): gi(f'ワイド払戻金{i}（円）') for i in (1, 2, 3) if gi(f'ワイド組番{i}馬番1')},
             '３連複': {tuple(sorted((gi('３連複組番馬番1'), gi('３連複組番馬番2'), gi('３連複組番馬番3')))): gi('３連複払戻金（円）')},
             '３連単': {(gi('３連単組番馬番1'), gi('３連単組番馬番2'), gi('３連単組番馬番3')): gi('３連単払戻金（円）')}}
        pays[k] = d
        a, b, c = gi('３連単組番馬番1'), gi('３連単組番馬番2'), gi('３連単組番馬番3')
        if not a:
            a = gi('単勝組番'); b = gi('馬単組番2')
        fins[k] = {a: 1, b: 2, c: 3}
races = defaultdict(list)
for t in csvs(odds_blob, 'odds'):
    for r in csv.reader(io.StringIO(t)):
        if not r or r[0] == '競馬場':
            continue
        races[(r[0], r[1], r[2])].append(r)
os.makedirs('data/nar', exist_ok=True)
f1 = gzip.open(f'data/nar/full_{Y}{M:02d}.csv.gz', 'wt', encoding='utf-8', newline='')
f2 = gzip.open(f'data/nar/prob_{Y}{M:02d}.csv.gz', 'wt', encoding='utf-8', newline='')
w1 = csv.writer(f1); w1.writerow(['場', '日', 'R', '頭数', '式', '組', 'o', 'omax', 'p', 'pay'])
w2 = csv.writer(f2); w2.writerow(['場', '日', 'R', '頭数', '馬番', 'pw', 'p2', 'p3', 'tan', 'fuku_lo', 'fuku_hi', 'fin'])
n1 = n2 = nr = 0; sums = []
for k, rows in races.items():
    if k not in pays or k[0].startswith('帯広'):
        continue
    q = {}
    for r in rows:
        if r[3] == '３連単':
            try:
                o = float(r[7])
                if o > 0:
                    q[(int(r[4]), int(r[5]), int(r[6]))] = 1 / o
            except Exception:
                pass
    s = sum(q.values())
    if s == 0:
        continue
    horses = sorted({h for c in q for h in c}); nh = len(horses)
    P = defaultdict(float); PW = defaultdict(float); P2 = defaultdict(float); P3 = defaultdict(float)
    for (a, b, c), x in q.items():
        x /= s
        P[('３連単', (a, b, c))] = x
        PW[a] += x; P2[a] += x; P2[b] += x; P3[a] += x; P3[b] += x; P3[c] += x
        P[('単勝', (a,))] += x
        for h in ((a, b) if nh <= 7 else (a, b, c)):
            P[('複勝', (h,))] += x
        P[('馬複', tuple(sorted((a, b))))] += x; P[('馬単', (a, b))] += x
        for pr in ((a, b), (a, c), (b, c)):
            P[('ワイド', tuple(sorted(pr)))] += x
        P[('３連複', tuple(sorted((a, b, c))))] += x
    sums.append(sum(PW.values()))
    tan = {}; fuku = {}
    for r in rows:
        kind = r[3]
        if kind not in ('単勝', '複勝', '馬複', '馬単', 'ワイド', '３連複', '３連単'):
            continue
        try:
            nums = tuple(int(v) for v in r[4:7] if v)
            o = float(r[7]); om = float(r[8]) if r[8] else ''
        except Exception:
            continue
        key = nums if kind in ('単勝', '複勝', '馬単', '３連単') else tuple(sorted(nums))
        p = P.get((kind, key), 0)
        pay = pays[k].get(kind, {}).get(key, 0)
        w1.writerow([k[0], k[1], k[2], nh, kind, '-'.join(map(str, nums)), o, om, round(p, 6), pay]); n1 += 1
        if kind == '単勝':
            tan[nums[0]] = o
        if kind == '複勝':
            fuku[nums[0]] = (o, om)
    for h in horses:
        w2.writerow([k[0], k[1], k[2], nh, h, round(PW[h], 6), round(P2[h], 6), round(P3[h], 6), tan.get(h, ''), fuku.get(h, ('', ''))[0], fuku.get(h, ('', ''))[1], fins[k].get(h, 0)]); n2 += 1
    nr += 1
f1.close(); f2.close()
print(f'{Y}/{M}: {nr}レース 組{n1}行 馬{n2}行 3連単確率の合計 平均{sum(sums)/len(sums):.4f}', flush=True)
