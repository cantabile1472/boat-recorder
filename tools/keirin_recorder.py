# 競輪：締切前（5分前・2分前・1分前・30秒前）と締切後のオッズ（3連単・ワイド・2車単・2車複）と結果を記録する（お金は賭けない）
# 情報元は KEIRIN.JP 系の「Kドリームス」。1分前の時点で戦略E（ワイド）を判定して通知する
import os, re, json, time, gzip, datetime, threading, urllib.request, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strat_e
JST = datetime.timezone(datetime.timedelta(hours=9))
now = lambda: datetime.datetime.now(JST)
RUN_MIN = float(os.environ.get('RUN_MINUTES', 330)); T0 = time.time()
B = 'https://keirin.kdreams.jp/'
TODAY = now(); HD = TODAY.strftime('%Y%m%d')
DDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', HD); os.makedirs(DDIR, exist_ok=True)
SN = [300, 120, 60, 30]          # 締切の何秒前に取るか
ESNAP = 3                         # 戦略Eで通知するスナップ（3 = 1分前）


def log(m):
    t = f'[{now():%H:%M:%S}] 競輪 {m}'
    print(t, flush=True)
    try:
        open(os.path.join(DDIR, 'keirin_run_log.txt'), 'a', encoding='utf-8').write(t + '\n')
    except Exception:
        pass


def get(u):
    for _ in range(3):
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)', 'Accept-Encoding': 'gzip', 'Accept-Language': 'ja'})
            with urllib.request.urlopen(rq, timeout=25) as r:
                b = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    b = gzip.decompress(b)
                return b.decode('utf-8', 'replace')
        except Exception:
            time.sleep(1.5)
    return ''


def txt(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s)).strip()


def section(h, key):
    i = h.find(f'id="JS_ODDSCONTENTS_{key}"')
    if i < 0:
        return ''
    j = h.find('id="JS_ODDSCONTENTS_', i + 30)
    return h[i: j if j > 0 else len(h)]


def parse_3t(h):
    """3連単：1着ごとの表。列見出し（num_header）が2着、各セルの見出しが3着"""
    sec = section(h, '3rentan')
    out = {}
    for tb in re.findall(r'<table class="odds_table b5[^"]*">(.*?)</table>', sec, re.S):
        m = re.search(r'<th rowspan="\d+" class="num_\d+">(\d+)</th>', tb)
        if not m:
            continue
        a = m.group(1); cols = []
        for row in re.findall(r'<tr>(.*?)</tr>', tb, re.S):
            hd = re.findall(r'<th colspan="2" class="num_\d+ num_header">(\d+)</th>', row)
            if hd:
                cols = hd; continue
            pairs = re.findall(r'<th class="num_\d+">(\d+)</th>\s*<td><span>([^<]*)</span></td>', row)
            for k, (c, v) in enumerate(pairs):
                if k < len(cols):
                    out[f'{a}-{cols[k]}-{c}'] = v.strip()
    return out


def parse_2(h, key):
    """ワイド・2車単・2車複：列ごとに『縦にまたがる見出し（1車目）→見出し（2車目）→値』"""
    sec = section(h, key)
    m = re.search(r'<table class="odds_table">(.*?)</table>', sec, re.S)
    if not m:
        return {}
    out = {}; first = {}
    for row in re.findall(r'<tr>(.*?)</tr>', m.group(1), re.S):
        slot = 0
        for tok in re.finditer(r'<th rowspan="\d+" class="num_\d+">(\d+)</th>|<th class="num_\d+">(\d+)</th>\s*<td><span>([^<]*)</span></td>', row):
            if tok.group(1):
                first[slot] = tok.group(1)
            else:
                if slot in first:
                    out[f'{first[slot]}-{tok.group(2)}'] = tok.group(3).replace(' ', '')
                slot += 1
    return out


def deadline(h):
    m = re.search(r'投票締切\s*(\d{1,2}):(\d{2})', txt(h))
    if not m:
        return None
    return TODAY.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)


def page_date_ok(h):
    return f'{TODAY:%Y年%m月%d日}' in txt(h)[:4000] or f'{TODAY:%Y年%m月%d日}' in h


def place_name(h):
    m = re.search(r'([^\s>]{1,6})競輪 レース詳細', txt(h))
    return m.group(1) if m else ''


def parse_result(h):
    """結果ページの払戻：[(券種, 組, 円)]"""
    i = h.find('<!-- 結果・払戻金')
    seg = h[i:] if i >= 0 else h
    out, kind = [], ''
    for tok in re.finditer(r'<th[^>]*>([^<]+)</th>|<dt class="number">([^<]+)</dt>\s*<dd class="refund"><span class="amount">([\d,]+)円', seg):
        if tok.group(1):
            kind = tok.group(1).strip()
        else:
            out.append([kind, tok.group(2).strip(), int(tok.group(3).replace(',', ''))])
    return out


def races_today():
    ids = set()
    for u in [f'{B}racecard/{TODAY:%Y/%m/%d}/', B + 'midnight/', B + 'nighter/']:
        ids |= set(re.findall(r'https://keirin\.kdreams\.jp/(\w+)/racedetail/(\d{16})/', get(u)))
    rs = []
    for v, rid in sorted(ids):
        h = get(f'{B}{v}/racedetail/{rid}/')
        if not h or not page_date_ok(h):
            continue
        dl = deadline(h)
        if dl:
            rs.append({'v': v, 'id': rid, 'R': int(rid[-2:]), 'dl': dl, 'name': place_name(h) or v, 'snap': 0})
        time.sleep(0.2)
    return rs


def save(rec, fn='keirin_odds.jsonl'):
    with open(os.path.join(DDIR, fn), 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False, separators=(',', ':')) + '\n')


def snap(x, tag):
    h = get(f"{B}{x['v']}/racedetail/{x['id']}/?pageType=odds&kakeshikiType=wide")
    if not h:
        return None
    nd = deadline(h)
    if nd and nd > x['dl'] and tag != 'close':
        x['dl'] = nd
        log(f"{x['name']}{x['R']}R 締切変更 → {nd:%H:%M}")
        return 'moved'
    m = re.search(r'id="JS_ODDSSTATUS_wide">\s*<p class="time">([^<]*)</p>', h)
    rec = {'snap': tag, 'time': f'{now():%H:%M:%S}', 'v': x['v'], 'name': x['name'], 'id': x['id'], 'R': x['R'],
           'dl': f"{x['dl']:%H:%M}", 'upd': m.group(1) if m else '',
           't3': parse_3t(h), 'wide': parse_2(h, 'wide'), 'ex': parse_2(h, '2shatan'), 'q': parse_2(h, '2shahuku')}
    save(rec)
    return rec


def e_eval(x, rec):
    wide = {}
    for k, v in rec['wide'].items():
        a, b = map(int, k.split('-'))
        lo, hi = strat_e.rng(v)
        if lo > 0:
            wide[(min(a, b), max(a, b))] = (lo, hi)
    tri = {tuple(map(int, k.split('-'))): strat_e.num(v) for k, v in rec['t3'].items()}
    oe = strat_e.evaluate({}, wide, tri, 3)
    strat_e.save(DDIR, f"競輪{rec['snap']}", x['name'], x['R'], f"{x['dl']:%H:%M}", oe)
    PE = strat_e.prm()
    if rec['snap'] == ESNAP and PE.get('notify') and 'keirin' in PE['sports']:
        le = strat_e.lines(oe, '番車')
        if le:
            strat_e.notify(f"【E】競輪 {x['name']} {x['R']}R 締切{x['dl']:%H:%M}", '\n'.join(le))
            log(f"【E】{x['name']}{x['R']}R " + ' / '.join(le))


PS = [(3600, '60分前'), (1800, '30分前'), (900, '15分前'), (600, '10分前'), (300, '5分前'), (180, '3分前'), (120, '2分前'), (60, '1分前')]


def pub(x, label):
    """公開データベース用（記録のみ・公開は未定）：keirin_pub.jsonl"""
    try:
        h = get(f"{B}{x['v']}/racedetail/{x['id']}/?pageType=odds&kakeshikiType=wide")
        if not h:
            return
        m = re.search(r'id="JS_ODDSSTATUS_wide">\s*<p class="time">([^<]*)</p>', h)
        save({'label': label, 'sec': int((x['dl'] - now()).total_seconds()), 'time': f'{now():%H:%M:%S}', 'v': x['v'], 'name': x['name'], 'id': x['id'], 'R': x['R'],
              'deadline': f"{x['dl']:%H:%M}", 'upd': m.group(1) if m else '', 't3': parse_3t(h), 'wide': parse_2(h, 'wide'), 'ex': parse_2(h, '2shatan'), 'q': parse_2(h, '2shahuku')}, 'keirin_pub.jsonl')
    except Exception as e:
        log(f"公開用の記録NG {x.get('name')}{x.get('R')}R {label} {e!r}")


def main():
    if now().hour < 7:
        return
    rs = races_today()
    done = {}
    p = os.path.join(DDIR, 'keirin_odds.jsonl')
    if os.path.exists(p):
        for l in open(p, encoding='utf-8'):
            try:
                d = json.loads(l)
                if isinstance(d['snap'], int):
                    done[d['id']] = max(done.get(d['id'], 0), d['snap'])
                else:
                    done[d['id'] + d['snap']] = 1
            except Exception:
                pass
    for x in rs:
        x['snap'] = done.get(x['id'], 0)
        x['closed'] = (x['id'] + 'close') in done
        x['res'] = (x['id'] + 'result') in done
    rs = [x for x in rs if x['dl'] > now() - datetime.timedelta(minutes=30)]
    pd_ = set(); pp = os.path.join(DDIR, 'keirin_pub.jsonl')
    if os.path.exists(pp):
        for l in open(pp, encoding='utf-8'):
            try:
                d = json.loads(l); pd_.add((d['id'], d['label']))
            except Exception:
                pass
    for x in rs:
        x['pubd'] = {lb for (i, lb) in pd_ if i == x['id']}
    morning = [x for x in rs if not x['pubd'] and (x['dl'] - now()).total_seconds() > 3700]
    for x in morning:
        x['pubd'].add('朝一')
    log(f"開催 {'・'.join(sorted({x['name'] for x in rs}))} / これから {len(rs)}レース")
    while time.time() - T0 < RUN_MIN * 60 and rs:
        if morning:
            pub(morning.pop(0), '朝一')
        for x in list(rs):
            sec = (x['dl'] - now()).total_seconds()
            for ps, lb in PS:
                if lb not in x['pubd'] and ps - 25 < sec <= ps:
                    x['pubd'].add(lb); pub(x, lb)
                elif lb not in x['pubd'] and sec <= ps - 25:
                    x['pubd'].add(lb)
            try:
                if x['snap'] < len(SN) and 3 < sec <= SN[x['snap']]:
                    while x['snap'] + 1 < len(SN) and sec <= SN[x['snap'] + 1]:
                        x['snap'] += 1          # 途中から始まったときは近いスナップへ
                    x['snap'] += 1
                    rec = snap(x, x['snap'])
                    if rec == 'moved':
                        x['snap'] = 0
                    elif rec and x['snap'] in (2, 3):
                        e_eval(x, rec)
                elif not x['closed'] and sec < -90:
                    x['closed'] = True
                    snap(x, 'close')
                elif not x['res'] and sec < -900:
                    x['res'] = True
                    h = get(f"{B}{x['v']}/racedetail/{x['id']}/?pageType=showResult")
                    pay = parse_result(h)
                    if pay:
                        save({'snap': 'result', 'time': f'{now():%H:%M:%S}', 'v': x['v'], 'name': x['name'], 'id': x['id'], 'R': x['R'], 'pay': pay})
                    rs.remove(x)
                elif sec < -1800:
                    rs.remove(x)
            except Exception as e:
                log('NG ' + repr(e))
        time.sleep(2)
    log('監視おわり')


if __name__ == '__main__':
    main()
