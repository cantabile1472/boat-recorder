# 指定日の競艇レースの出走表（級別・勝率・モーター）と直前情報（展示タイム・風・波）を取って保存する
import sys, os, re, time, csv, urllib.request, gzip
HD = sys.argv[1]
KB = 'https://www.boatrace.jp/owpc/pc/race/'
def get(u):
    for _ in range(3):
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'})
            with urllib.request.urlopen(rq, timeout=30) as r:
                b = r.read()
                if r.headers.get('Content-Encoding') == 'gzip': b = gzip.decompress(b)
                return b.decode('utf-8', 'replace')
        except Exception:
            time.sleep(2)
    return ''
def num(s):
    try: return float(re.sub(r'[^\d.]', '', s))
    except Exception: return ''
def split_boats(h):
    parts = re.split(r'is-boatColor(\d) is-fs14" rowspan="4">', h)
    o = {}
    for k in range(1, len(parts) - 1, 2):
        b = int(parts[k]); o.setdefault(b, parts[k + 1])
    return o
idx = get(f'{KB}index?hd={HD}')
jcds = sorted(set(re.findall(r'jcd=(\d\d)', idx)))
out = []
for j in jcds:
    for r in range(1, 13):
        q = f'?rno={r}&jcd={j}&hd={HD}'
        rl = get(KB + 'racelist' + q); bi = get(KB + 'beforeinfo' + q)
        if not rl: continue
        bl = split_boats(rl); bb = split_boats(bi)
        ws = re.search(r'風速</span>\s*<span class="weather1_bodyUnitLabelData">\s*(\d+)m', bi)
        wv = re.search(r'波高</span>\s*<span class="weather1_bodyUnitLabelData">\s*(\d+)cm', bi)
        wt = re.search(r'水温</span>\s*<span class="weather1_bodyUnitLabelData">\s*([\d.]+)', bi)
        for b in range(1, 7):
            t = bl.get(b, '')
            m = re.search(r'\d{4}\s*/\s*<span class="[^"]*">\s*([AB][12])\s*</span>', t)
            L = re.findall(r'is-lineH2"\s+rowspan="4">\s*([^<]*)<br\s*/>\s*([^<]*)<br\s*/>\s*([^<]*)</td>', t)
            tm = re.search(r'<td rowspan="4">\s*(\d\.\d\d)\s*</td>', bb.get(b, ''))
            out.append([j, r, b, m.group(1) if m else '', num(L[1][0]) if len(L) > 1 else '', num(L[1][1]) if len(L) > 1 else '',
                        num(L[3][1]) if len(L) > 3 else '', tm.group(1) if tm else '',
                        ws.group(1) if ws else '', wv.group(1) if wv else '', wt.group(1) if wt else ''])
        time.sleep(0.2)
os.makedirs(f'data/{HD}', exist_ok=True)
with open(f'data/{HD}/kyotei_info.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f); w.writerow(['jcd', 'R', 'boat', 'cls', 'nat', 'loc', 'mot', 'tenji', 'ws', 'wv', 'wtemp']); w.writerows(out)
print(HD, len(out), '行')
