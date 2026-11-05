# 過去日の競艇：締切オッズ（単勝・複勝・ワイド・3連単）と複勝・ワイドの払戻を取って、data/kclose/YYYYMMDD.csv.gz に保存する
# 使い方: python tools/backfill_close.py 20261001 20261002 ...
import sys, os, re, time, gzip, csv, io, urllib.request
from concurrent.futures import ThreadPoolExecutor
KB = 'https://www.boatrace.jp/owpc/pc/race/'
os.makedirs('data/kclose', exist_ok=True)


def get(u):
    for _ in range(3):
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'})
            with urllib.request.urlopen(rq, timeout=20) as r:
                b = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    b = gzip.decompress(b)
                return b.decode('utf-8', 'replace')
        except Exception:
            time.sleep(2)
    return ''


def pts(h):
    return [re.sub(r'\s+', '', v) for v in re.findall(r'oddsPoint[^>]*>([^<]*)<', h)]


def pays(h):
    out = []
    for nm, kd in [('拡連複', 'ワイド'), ('複勝', '複勝')]:
        i = h.find('>' + nm + '<')
        if i < 0:
            continue
        seg = h[i: h.find('</tbody>', i)]
        for row in re.split(r'<tr', seg):
            nums = re.findall(r'numberSet1_number[^>]*>(\d)</span>', row)
            pay = re.search(r'&yen;([\d,]+)', row)
            if nums and pay:
                out.append(f"{kd}:{'-'.join(sorted(nums))}:{pay.group(1).replace(',', '')}")
    return ' '.join(out)


def one(args):
    hd, j, r = args
    q = f'?rno={r}&jcd={j}&hd={hd}'
    res = get(KB + 'raceresult' + q)
    if '>複勝<' not in res:
        return None
    tf, k, t3 = get(KB + 'oddstf' + q), get(KB + 'oddsk' + q), get(KB + 'odds3t' + q)
    a, b, c = pts(tf), pts(k), pts(t3)
    if len(c) != 120 or len(a) < 12:
        return None
    return [j, r, ' '.join(a), ' '.join(b), ' '.join(c), pays(res)]


for hd in sys.argv[1:]:
    fn = f'data/kclose/{hd}.csv.gz'
    if os.path.exists(fn):
        continue
    idx = get(f'{KB}index?hd={hd}')
    jcds = sorted(set(re.findall(r'jcd=(\d\d)', idx)))
    with ThreadPoolExecutor(8) as ex:
        rows = [x for x in ex.map(one, [(hd, j, r) for j in jcds for r in range(1, 13)]) if x]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['jcd', 'R', 'tf', 'k', 't3', 'pay'])
    w.writerows(rows)
    with gzip.open(fn, 'wt', encoding='utf-8') as f:
        f.write(buf.getvalue())
    print(hd, len(jcds), '場', len(rows), 'レース', flush=True)
