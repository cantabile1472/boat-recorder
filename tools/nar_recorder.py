# 地方競馬：締切前（発走6分前・4分前・3分前・2分半前）の全券種オッズを記録する（お金は賭けない）
# 締切時のオッズと払戻は、あとで公式の月別データから取る
import os, re, json, time, gzip, datetime, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strat_e
import nar_cards
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
PS = [(3600, '60分前'), (1800, '30分前'), (900, '15分前'), (600, '10分前'), (300, '5分前'), (180, '3分前'), (120, '2分前'), (60, '1分前')]   # 締切（発走2分前）の何秒前


def pub(x, label):
    """公開データベース用：全券種を1回分記録（nar_pub.jsonl）。締切は発走の2分前として扱う"""
    try:
        q = f"?k_raceDate={DS}&k_raceNo={x['R']}&k_babaCode={x['bc']}"
        close = x['post'] - datetime.timedelta(minutes=2)
        rec = {'label': label, 'sec': int((close - now()).total_seconds()), 'time': f'{now():%H:%M:%S}', 'bc': x['bc'], 'place': BABA.get(str(int(x['bc'])), x['bc']),
               'R': x['R'], 'post': f"{x['post']:%H:%M}", 'deadline': f"{close:%H:%M}"}
        with ThreadPoolExecutor(2) as ex:
            res = dict(zip(PAGES, ex.map(lambda p: get(B + PAGES[p] + q), PAGES)))
        rec['tf'] = tanfuku(res['tf'])
        for k in ('wide', 'q', 'ex', 'tri', 'tri3'): rec[k] = rank_table(res[k])
        if rec['tf']:
            with LOCK:
                with open(os.path.join(DDIR, 'nar_pub.jsonl'), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(rec, ensure_ascii=False, separators=(',', ':')) + '\n')
    except Exception as e:
        log(f"公開用の記録NG {x.get('bc')} {x.get('R')}R {label} {e!r}")


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
    if x['snap'] == 1 or (x['snap'] in (2, 3) and not x.get('cards')):
        try:
            hd_ = get(B + 'DebaTable' + q)
            x['cards'] = nar_cards.parse_deba(hd_) if hd_ else {}
            t = nar_cards.txt(hd_[:20000]) if hd_ else ''
            x['title'] = (re.search(r'発走\s*(.*?)(?:ダート|芝|サラブレッド)', t) or [None, ''])[1]
        except Exception as e:
            log('出馬表NG ' + repr(e)); x['cards'] = x.get('cards') or {}
    if x['snap'] == 3:
        try:
            g_nar(x, rec)
        except Exception as e:
            log('戦略G(地方) NG ' + repr(e))
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
GN_RULES = [
    # 2〜3番人気（3連単換算）の単勝
    ('N1 2〜3番人気・前走6着以下・通算10走未満・単勝と3連単が一致', lambda h: h['rank'] in (2, 3) and h['p1_fin'] >= 6 and h['rec_n'] < 10 and 0.9 <= h['gap'] <= 1.1),
    ('N2 2〜3番人気・前走6着以下・通算10走未満・1番人気が50%未満', lambda h: h['rank'] in (2, 3) and h['p1_fin'] >= 6 and h['rec_n'] < 10 and h['pw1'] < 0.5),
    ('N3 2〜3番人気・前走6着以下・過去走1〜2・1番人気が50%未満', lambda h: h['rank'] in (2, 3) and h['p1_fin'] >= 6 and 1 <= h['npast'] <= 2 and h['pw1'] < 0.5),
    ('N4 2〜3番人気・前走6着以下・通算10走未満・3歳戦', lambda h: h['rank'] in (2, 3) and h['p1_fin'] >= 6 and h['rec_n'] < 10 and '３歳' in h['title']),
    ('N5 2〜3番人気・換算25%以上・通算10走未満・単勝が3連単より弱気', lambda h: h['rank'] in (2, 3) and h['pw'] >= 0.25 and h['rec_n'] < 10 and h['gap'] < 0.85),
    # 大本命の単勝
    ('N6 大本命・前走4着以下・換算70%以上・笠松浦和川崎以外', lambda h: h['rank'] == 1 and h['pw'] >= 0.7 and h['p1_fin'] >= 4 and h['place'] not in ('笠松', '浦和', '川崎')),
    ('N7 大本命・前走4着以下・換算70%以上', lambda h: h['rank'] == 1 and h['pw'] >= 0.7 and h['p1_fin'] >= 4),
    ('N8 大本命・前走4人気以下・換算70%以上', lambda h: h['rank'] == 1 and h['pw'] >= 0.7 and h['p1_pop'] >= 4),
    ('N9 大本命・水沢/佐賀・換算70%以上', lambda h: h['rank'] == 1 and h['pw'] >= 0.7 and h['place'] in ('水沢', '佐賀')),
]


def g_nar(x, rec):
    """戦略G（地方）：締切1分前に、3連単換算の順位・勝率と出馬表の情報で単勝の買い目を判定して通知（ばんえいは対象外）"""
    if str(int(x['bc'])) == '3':
        return
    cfgv = {}
    try:
        cfgv = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json'), encoding='utf-8')).get('strategy_G_nar', {})
    except Exception:
        pass
    if cfgv and not cfgv.get('notify', True):
        return
    fuku, wide, tri, nf = strat_e.nar_parse(rec)
    pw = {}
    for (a, b, c), v in tri.items():
        if v > 0:
            pw[a] = pw.get(a, 0) + 1 / v
    s = sum(pw.values())
    if s <= 0:
        return
    pw = {k: v / s for k, v in pw.items()}
    tan = {int(r[0]): strat_e.num(r[1]) for r in rec['tf'] if strat_e.num(r[1]) > 0}
    S = sum(1 / v for v in tan.values())
    order = sorted(pw, key=lambda k: -pw[k]); pw1 = pw[order[0]]
    nm = BABA.get(str(int(x['bc'])), x['bc']); close = x['post'] - datetime.timedelta(minutes=2)
    cards = x.get('cards') or {}
    hits = []
    for hn in order[:3]:
        if hn not in tan:
            continue
        c = cards.get(hn, {}); past = [p for p in (c.get('past') or []) if p]
        p1 = past[0] if past else {}
        h = {'rank': order.index(hn) + 1, 'pw': pw[hn], 'pw1': pw1, 'gap': ((1 / tan[hn]) / S) / pw[hn], 'tan': tan[hn],
             'p1_fin': p1.get('fin') if isinstance(p1.get('fin'), int) else 0, 'p1_pop': p1.get('pop') or 0, 'npast': len(past),
             'rec_n': sum(c.get('rec_all') or [0]), 'title': x.get('title', ''), 'place': nm}
        rules = [n for n, f in GN_RULES if f(h)]
        with LOCK:
            with open(os.path.join(DDIR, 'g_nar_log.csv'), 'a', encoding='utf-8') as f:
                if f.tell() == 0:
                    f.write('time,place,R,close,num,rank,tan,pw,pw1,gap,p1_fin,p1_pop,npast,rec_n,rules\n')
                f.write(f"{now():%H:%M:%S},{nm},{x['R']},{close:%H:%M},{hn},{h['rank']},{h['tan']},{h['pw']:.4f},{h['pw1']:.4f},{h['gap']:.3f},{h['p1_fin']},{h['p1_pop']},{h['npast']},{h['rec_n']},{' / '.join(r.split(' ')[0] for r in rules)}\n")
        if rules:
            hits.append((hn, h, rules))
    nmin = int(cfgv.get('min_rules', 2)); nstar = int(cfgv.get('star_rules', 3))
    for hn, h, rules in hits:
        if len(rules) < nmin:
            continue
        star = '★' * (len(rules) >= nstar)
        body = (f"{hn}番 単勝 今{h['tan']:.1f}倍 3連単換算の勝率{h['pw']*100:.0f}%（{h['rank']}番人気） 単勝÷3連単{h['gap']:.2f}\n"
                f"前走{h['p1_fin']}着・前走{h['p1_pop']}人気・通算{h['rec_n']}走・1番人気の換算{h['pw1']*100:.0f}%\n" + '\n'.join('・' + r for r in rules))
        strat_e.notify(f"{star}【G{len(rules)}】{star}地方競馬 {nm} {x['R']}R 締切{close:%H:%M}頃（発走{x['post']:%H:%M}）", body)
        log(f"【G{len(rules)}】{star}{nm}{x['R']}R {hn}番 " + ' / '.join(rules))


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
    pd_ = set(); pp = os.path.join(DDIR, 'nar_pub.jsonl')
    if os.path.exists(pp):
        for l in open(pp, encoding='utf-8'):
            try:
                d = json.loads(l); pd_.add((d['bc'], d['R'], d['label']))
            except Exception: pass
    PR = [dict(x, pubd={lb for (b, r, lb) in pd_ if b == x['bc'] and r == x['R']}) for x in rs if x['post'] - datetime.timedelta(minutes=2) > now()]
    morning = [x for x in PR if not x['pubd'] and (x['post'] - now()).total_seconds() > 3820]
    for x in morning: x['pubd'].add('朝一')
    rs = [x for x in rs if x['post'] > now() + datetime.timedelta(seconds=150)]
    log(f'開催 {len(babas)}場 / これから {len(rs)}レース（公開用 {len(PR)}レース・朝一 {len(morning)}）')
    while time.time() - T0 < RUN_MIN * 60 and (rs or PR):
        if morning:
            pub(morning.pop(0), '朝一')
        for x in list(PR):
            sec = (x['post'] - now()).total_seconds() - 120
            if sec < 30:
                PR.remove(x); continue
            for ps, lb in PS:
                if lb not in x['pubd'] and ps - 25 < sec <= ps:
                    x['pubd'].add(lb); pub(x, lb)
                elif lb not in x['pubd'] and sec <= ps - 25:
                    x['pubd'].add(lb)
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
