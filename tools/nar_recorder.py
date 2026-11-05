# 地方競馬：締切前（発走6分前・4分前・3分前・2分半前）の全券種オッズを記録する（お金は賭けない）
# 締切時のオッズと払戻は、あとで公式の月別データから取る
import os, re, json, time, gzip, datetime, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strat_e
BABA = {'3': '帯広', '10': '盛岡', '11': '水沢', '18': '浦和', '19': '船橋', '20': '大井', '21': '川崎', '22': '金沢', '23': '笠松', '24': '名古屋', '27': '園田', '28': '姫路', '31': '高知', '32': '佐賀', '36': '門別'}
JST = datetime.timezone(datetime.timedelta(hours=9))
now = lambda: datetime.datetime.now(JST)
RUN_MIN = float(os.environ.get('RUN_MINUTES', 330)); T0 = time.time()
B = 'https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/'
TODAY = now(); HD = TODAY.strftime('%Y%m%d'); DS = TODAY.strftime('%Y%%2F%m%%2F%d')
DDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', HD); os.makedirs(DDIR, exist_ok=True)
LOCK = threading.Lock()
SN = [360, 240, 180, 150, 60]   # 発走の何秒前に取るか（締切は発走の約2分前。最後の60秒前は締切後＝最終オッズ）
PAGES = {'tf': 'OddsTanFuku', 'wide': 'OddsWide', 'q': 'OddsUmLenFuku', 'ex': 'OddsUmLenTan', 'tri': 'Odds3LenFuku', 'tri3': 'Odds3LenTan'}
def log(m):
    print(f'[{now():%H:%M:%S}] 地方 {m}', flush=True)
def get(u):
    for _ in range(2):
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'})
            with urllib.request.urlopen(rq, timeout=20) as r:
                b = r.read()
                if r.headers.get('Content-Encoding') == 'gzip': b = gzip.decompress(b)
                return b.decode('utf-8', 'replace')
        except Exception: time.sleep(1)
    return ''
def rank_table(h):
    out = []
    for combo, cell in re.findall(r'<td[^>]*>\s*(\d+(?:-\d+){0,2})\s*</td>\s*<td[^>]*>(.*?)</td>', h, re.S):
        nums = re.findall(r'[\d.]+', cell)
        if nums: out.append([combo] + nums[:2])
    return out
def tanfuku(h):
    i = h.find('odd_popular_table'); h = h[i:] if i >= 0 else h
    out = []
    for row in re.findall(r'<tr>(.*?)</tr>', h, re.S):
        tds = [re.sub(r'<[^>]+>', ' ', t).strip() for t in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
        if len(tds) >= 6 and tds[1].isdigit():
            out.append([tds[1], tds[3], tds[4].rstrip('-').strip(), tds[5]])
    return out
def races_today():
    top = get(B + 'TodayRaceInfoTop')
    babas = sorted(set(re.findall(r'RaceList\?k_raceDate=' + re.escape(DS) + r'&amp;k_babaCode=(\d+)', top)))
    rs = []
    for bc in babas:
        for rn in range(1, 13):
            h = get(f'{B}DebaTable?k_raceDate={DS}&k_raceNo={rn}&k_babaCode={bc}')
            m = re.search(r'第\s*\d+\s*競走\s*(\d{1,2}):(\d{2})発走', re.sub(r'<[^>]+>', ' ', h))
            if not m: 
                if rn > 1 and not h: break
                continue
            post = TODAY.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
            rs.append({'bc': bc, 'R': rn, 'post': post, 'snap': 0})
            time.sleep(0.2)
    return babas, rs
def snap(x):
    q = f"?k_raceDate={DS}&k_raceNo={x['R']}&k_babaCode={x['bc']}"
    rec = {'snap': x['snap'], 'time': f'{now():%H:%M:%S}', 'bc': x['bc'], 'R': x['R'], 'post': f"{x['post']:%H:%M}"}
    with ThreadPoolExecutor(6) as ex:
        res = dict(zip(PAGES, ex.map(lambda p: get(B + PAGES[p] + q), PAGES)))
    rec['tf'] = tanfuku(res['tf'])
    for k in ('wide', 'q', 'ex', 'tri', 'tri3'): rec[k] = rank_table(res[k])
    with LOCK:
        with open(os.path.join(DDIR, 'nar_odds.jsonl'), 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(',', ':')) + '\n')
    if x['snap'] in (2, 3):
        try:
            oe = strat_e.evaluate(*strat_e.nar_parse(rec))
            nm = BABA.get(str(int(x['bc'])), x['bc'])
            close = x['post'] - datetime.timedelta(minutes=2)
            strat_e.save(DDIR, f"地方{x['snap']}", nm, x['R'], f"{close:%H:%M}", oe)
            PE = strat_e.prm()
            if x['snap'] == 3 and PE.get('notify') and 'nar' in PE['sports']:
                le = strat_e.lines(oe, '番')
                if le:
                    strat_e.notify(f"【E】地方競馬 {nm} {x['R']}R 締切{close:%H:%M}頃（発走{x['post']:%H:%M}）", '\n'.join(le))
                    log(f"【E】{nm}{x['R']}R " + ' / '.join(le))
        except Exception as e:
            log('戦略E NG ' + repr(e))
    if not os.path.exists(os.path.join(DDIR, 'nar_tanfuku_sample.html')):
        open(os.path.join(DDIR, 'nar_tanfuku_sample.html'), 'w', encoding='utf-8').write(res['tf'])
    return len(rec['tf']), len(rec['tri3'])
def main():
    n = now()
    if n.hour < 9 or n.hour >= 21: return
    babas, rs = races_today()
    done = set()
    p = os.path.join(DDIR, 'nar_odds.jsonl')
    if os.path.exists(p):
        for l in open(p, encoding='utf-8'):
            try:
                d = json.loads(l); done.add((d['bc'], d['R'], d['snap']))
            except Exception: pass
    for x in rs:
        x['snap'] = max([s for (b, r, s) in done if b == x['bc'] and r == x['R']] + [0])
    rs = [x for x in rs if x['post'] > now() + datetime.timedelta(seconds=150)]
    log(f'開催 {len(babas)}場 / これから {len(rs)}レース')
    while time.time() - T0 < RUN_MIN * 60 and rs:
        for x in list(rs):
            sec = (x['post'] - now()).total_seconds()
            if x['snap'] >= len(SN) or sec < 30:
                rs.remove(x); continue
            if sec <= SN[x['snap']]:
                x['snap'] += 1
                try:
                    a, b = snap(x)
                    if x['snap'] == 1: log(f"{x['bc']} {x['R']}R 記録（単複{a}頭・3連単{b}組）")
                except Exception as e:
                    log('NG ' + repr(e))
        time.sleep(3)
    log('監視おわり')
if __name__ == '__main__':
    main()
