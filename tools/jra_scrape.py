# JRA：netkeiba から結果（着順・単勝締切オッズ・人気）と出馬表の過去5走を取って data/jra/YYYYMM.jsonl.gz に保存（1行=1レース）
#  使い方: python tools/jra_scrape.py 20260101 20260131
import sys, os, re, json, gzip, time, datetime, urllib.request
from concurrent.futures import ThreadPoolExecutor
os.makedirs('data/jra', exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'}


def get(u, enc):
    for _ in range(3):
        try:
            rq = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(rq, timeout=30) as r:
                return r.read().decode(enc, 'replace')
        except Exception:
            time.sleep(3)
    return ''


def txt(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s.replace('&nbsp;', ' '))).strip()


def race_ids(ymd):
    h = get(f'https://db.netkeiba.com/race/list/{ymd}/', 'euc-jp')
    return sorted(set(re.findall(r'/race/(\d{12})/', h)))


def parse_result(h):
    race = {}
    m = re.search(r'class="racedata fc">(.*?)</dl>', h, re.S)
    t = txt(m.group(1)) if m else ''
    race['title'] = t[:120]
    m = re.search(r'(芝|ダ|障)[^0-9]*?(\d{3,4})m', t); race['surface'], race['dist'] = (m.group(1), int(m.group(2))) if m else ('', None)
    m = re.search(r'(\d{4})年(\d+)月(\d+)日', h); race['day'] = f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}" if m else ''
    m = re.search(r'<p class="smalltxt">(.*?)</p>', h, re.S); race['cond'] = txt(m.group(1)) if m else ''
    i = h.find('race_table_01'); seg = h[i:h.find('</table>', i)]
    horses = []
    for row in re.findall(r'<tr>(.*?)</tr>', seg, re.S):
        c = [txt(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
        if len(c) < 12:
            continue
        hid = re.search(r'/horse/(\d+)/', row)
        try:
            fin = int(c[0])
        except Exception:
            fin = c[0]
        # 単勝・人気は末尾側から（タイム指数列などで列数が揺れるため）
        od = pop = None
        for k in range(len(c) - 1, 5, -1):
            if re.fullmatch(r'\d+(\.\d+)?', c[k]) and re.fullmatch(r'\d+', c[k - 1] if k - 1 >= 0 else '') and od is None:
                pass
        # 性齢の直後2つ: 斤量, 騎手。単勝=人気の直前の小数
        for k in range(len(c)):
            if re.fullmatch(r'\d+\.\d', c[k]) and k + 1 < len(c) and re.fullmatch(r'\d{1,2}', c[k + 1]) and k + 2 < len(c) and re.search(r'^\d{3}\(', c[k + 2] or ''):
                od, pop = float(c[k]), int(c[k + 1]); break
        horses.append({'fin': fin, 'num': int(c[2]) if c[2].isdigit() else None, 'name': c[3], 'hid': hid.group(1) if hid else '', 'sexage': c[4], 'wt': c[5], 'jockey': c[6], 'odds': od, 'pop': pop})
    race['horses'] = horses
    pays = {}
    for kind in ('単勝', '複勝', '馬単', '三連単', '3連単'):
        m = re.search(r'<th[^>]*>' + kind + r'</th>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>', h, re.S)
        if m:
            pays[kind] = (txt(m.group(1)), txt(m.group(2)))
    race['pays'] = pays
    return race


def parse_past(h):
    out = {}
    for blk in re.findall(r'<tr class="HorseList[^"]*"[^>]*>(.*?)</tr>', h, re.S):
        mm = re.search(r'<td class="Waku">(\d+)</td>', blk)
        if not mm:
            continue
        num = int(mm.group(1)); past = []
        for item in re.findall(r'<td class="Past[^"]*"[^>]*>(.*?)</td>', blk, re.S):
            d1 = re.search(r'<div class="Data01">(.*?)</div>', item, re.S); d3 = re.search(r'<div class="Data03">(.*?)</div>', item, re.S); d2 = re.search(r'<div class="Data02">(.*?)</div>', item, re.S)
            if not d1:
                continue
            t1 = txt(d1.group(1)); r = re.search(r'(\d{4}\.\d{2}\.\d{2})\s*(\S+)\s*(\d+)', t1)
            p = re.search(r'(\d+)頭\s*(\d+)番\s*(\d+)人', txt(d3.group(1)) if d3 else '')
            if r:
                past.append({'date': r.group(1), 'place': r.group(2), 'fin': int(r.group(3)), 'race': txt(d2.group(1))[:20] if d2 else '', 'nh': int(p.group(1)) if p else None, 'pop': int(p.group(3)) if p else None})
        hid = re.search(r'/horse/(\d+)', blk)
        out[num] = past
    return out


def one(rid):
    hr = get(f'https://db.netkeiba.com/race/{rid}/', 'euc-jp')
    if 'race_table_01' not in hr:
        return None
    race = parse_result(hr); race['id'] = rid
    hp = get(f'https://race.netkeiba.com/race/shutuba_past.html?race_id={rid}', 'utf-8')
    past = parse_past(hp) if hp else {}
    for x in race['horses']:
        x['past'] = past.get(x['num'], [])
    time.sleep(0.5)
    return race


if __name__ == '__main__':
    d0 = datetime.datetime.strptime(sys.argv[1], '%Y%m%d'); d1 = datetime.datetime.strptime(sys.argv[2], '%Y%m%d')
    days = []
    d = d0
    while d <= d1:
        days.append(d.strftime('%Y%m%d')); d += datetime.timedelta(days=1)
    bymonth = {}
    for ymd in days:
        ids = race_ids(ymd)
        if ids:
            bymonth.setdefault(ymd[:6], []).extend(ids)
        time.sleep(0.3)
    for ym, ids in bymonth.items():
        fn = f'data/jra/{ym}.jsonl.gz'
        done = set()
        if os.path.exists(fn):
            done = {json.loads(l)['id'] for l in gzip.open(fn, 'rt', encoding='utf-8')}
        todo = [i for i in ids if i not in done]
        print(ym, len(ids), 'レース', '未取得', len(todo), flush=True)
        with ThreadPoolExecutor(3) as ex, gzip.open(fn, 'at', encoding='utf-8') as f:
            for k, r in enumerate(ex.map(one, todo)):
                if r:
                    f.write(json.dumps(r, ensure_ascii=False) + '\n')
                if k % 100 == 0:
                    print(k, flush=True)
