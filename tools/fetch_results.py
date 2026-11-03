# 指定日の競艇の結果（2連単・3連単の組と払戻）を取る
import sys, os, re, csv, glob, time, gzip, urllib.request
from concurrent.futures import ThreadPoolExecutor
HD = sys.argv[1]; KB = 'https://www.boatrace.jp/owpc/pc/race/'
def get(u):
    for _ in range(3):
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'})
            with urllib.request.urlopen(rq, timeout=15) as r:
                b = r.read()
                if r.headers.get('Content-Encoding') == 'gzip': b = gzip.decompress(b)
                return b.decode('utf-8', 'replace')
        except Exception: time.sleep(2)
    return ''
T = set()
for p in glob.glob(f'data/{HD}/kyotei_close*.csv'):
    for row in csv.DictReader(open(p, encoding='utf-8')): T.add((row['jcd'].zfill(2), int(row['R'])))
def one(jr):
    j, r = jr
    h = get(f'{KB}raceresult?rno={r}&jcd={j}&hd={HD}')
    out = [j, r]
    for nm, k in [('2連単', 2), ('3連単', 3)]:
        i = h.find('>' + nm + '<')
        seg = h[i:i + 1500] if i >= 0 else ''
        nums = re.findall(r'numberSet1_number[^>]*>(\d)</span>', seg)[:k]
        pay = re.search(r'&yen;([\d,]+)', seg)
        out += ['-'.join(nums), pay.group(1).replace(',', '') if pay else '']
    return out
with ThreadPoolExecutor(6) as ex: rows = list(ex.map(one, sorted(T)))
with open(f'data/{HD}/kyotei_result2.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f); w.writerow(['jcd', 'R', 'exacta', 'exacta_pay', 'trifecta', 'trifecta_pay']); w.writerows(rows)
print(HD, len(rows))
