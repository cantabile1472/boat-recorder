# 地方競馬：出馬表ページから血統（父・母・母の父）・馬主・生産牧場を取る
# 使い方: python tools/nar_pedigree.py data/nar/pedigree_races.csv  （day,bc,R の一覧）→ data/nar/pedigree.csv に追記
import os, re, sys, csv, time, gzip, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = 'https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/DebaTable'
def get(u):
    for _ in range(3):
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'})
            with urllib.request.urlopen(rq, timeout=20) as r:
                b = r.read()
                if r.headers.get('Content-Encoding') == 'gzip': b = gzip.decompress(b)
                return b.decode('utf-8', 'replace')
        except Exception:
            time.sleep(3)
    return ''
def clean(s): return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s)).strip()
def parse(h):
    out = {}
    for b in re.split(r'<td rowspan="5" class="horseNum">', h)[1:]:
        m = re.match(r'\s*(\d+)\s*<', b)
        if not m: continue
        seg = b[:b.find('<tr class="tBorder">')] if '<tr class="tBorder">' in b else b
        code = (re.search(r'k_lineageLoginCode=(\d+)', seg) or [None, ''])[1]
        cells = re.findall(r'<td colspan="3">([^<]*)</td>\s*<td colspan="1">(.*?)</td>', seg, re.S)
        if len(cells) < 3: continue
        out[int(m.group(1))] = {'code': code, 'sire': clean(cells[0][0]), 'dam': clean(cells[1][0]), 'damsire': clean(cells[2][0]).strip('（）()'),
                                'trainer_txt': clean(cells[0][1]), 'owner': clean(cells[1][1]), 'breeder': clean(cells[2][1])}
    return out
if __name__ == '__main__':
    src = sys.argv[1]; out = os.path.join(ROOT, 'data', 'nar', 'pedigree.csv')
    done = set()
    if os.path.exists(out):
        done = {(r['day'], r['bc'], r['R']) for r in csv.DictReader(open(out, encoding='utf-8'))}
    races = [r for r in csv.DictReader(open(src, encoding='utf-8')) if (r['day'], r['bc'], r['R']) not in done]
    if len(sys.argv) > 2: races = races[:int(sys.argv[2])]
    new = not os.path.exists(out); n = 0
    with open(out, 'a', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        if new: w.writerow(['day', 'bc', 'R', 'num', 'code', 'sire', 'dam', 'damsire', 'owner', 'breeder'])
        for r in races:
            d = r['day']
            h = get(f"{B}?k_raceDate={d[:4]}%2F{d[4:6]}%2F{d[6:]}&k_raceNo={r['R']}&k_babaCode={r['bc']}")
            P = parse(h)
            for num, v in sorted(P.items()):
                w.writerow([d, r['bc'], r['R'], num, v['code'], v['sire'], v['dam'], v['damsire'], v['owner'], v['breeder']])
            n += bool(P); f.flush(); time.sleep(1.2)
    print(len(races), 'レース中', n, 'レースで血統を取得')
