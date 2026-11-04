# 競艇・オートレース 締切前オッズ記録ツール（GitHub Actions 用）
# お金は賭けない。締切前（3分前・1分半前・40秒前・15秒前・5秒前）と締切のオッズ、結果を記録する。
import os, re, json, gzip, time, math, datetime, subprocess, traceback, threading
import urllib.request, urllib.parse, http.cookiejar
from concurrent.futures import ThreadPoolExecutor

JST = datetime.timezone(datetime.timedelta(hours=9))
ROOT = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(ROOT, 'config.json'), encoding='utf-8'))
RUN_MIN = float(os.environ.get('RUN_MINUTES', CFG.get('run_minutes', 335)))
TOPIC = os.environ.get('NTFY_TOPIC', '').strip()
SN = [200, 95, 42, 17, 7]
LAB = ['', '3分前', '1分半前', '40秒前・最終判定', '15秒前', '5秒前']
T0 = time.time()
LOCK = threading.Lock()
_CFG_T = [time.time()]


def cfg():
    """設定（config.json）を5分おきに GitHub から読み直す。書き換えたら動いている途中でも反映される"""
    global CFG
    if time.time() - _CFG_T[0] > 300 and not os.environ.get('NO_GIT'):
        _CFG_T[0] = time.time()
        try:
            subprocess.run(['git', 'fetch', '-q', 'origin', 'main'], cwd=ROOT, timeout=60)
            t = subprocess.run(['git', 'show', 'origin/main:config.json'], cwd=ROOT, capture_output=True, text=True, timeout=30).stdout
            new = json.loads(t)
            if new != CFG:
                CFG = new
                print('設定を読み直した', flush=True)
        except Exception as e:
            print('設定の読み直しNG', e, flush=True)
    return CFG


def now():
    return datetime.datetime.now(JST)


TODAY = now()
# 0時〜4時に動いているときは前日の開催として扱う（ミッドナイト対策）
if TODAY.hour < 4:
    TODAY = TODAY - datetime.timedelta(days=1)
HD = TODAY.strftime('%Y%m%d')
YMD = TODAY.strftime('%Y-%m-%d')
DDIR = os.path.join(ROOT, 'data', HD)
os.makedirs(DDIR, exist_ok=True)


def log(msg):
    line = f'[{now():%H:%M:%S}] {msg}'
    print(line, flush=True)
    with LOCK:
        with open(os.path.join(DDIR, 'run_log.txt'), 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def append_csv(name, header, rows):
    p = os.path.join(DDIR, name)
    with LOCK:
        new = not os.path.exists(p)
        with open(p, 'a', encoding='utf-8') as f:
            if new:
                f.write(header + '\n')
            for r in rows:
                f.write(','.join('' if v is None else str(v) for v in r) + '\n')


def read_csv(name):
    p = os.path.join(DDIR, name)
    if not os.path.exists(p):
        return []
    with LOCK:
        lines = open(p, encoding='utf-8').read().splitlines()
    if not lines:
        return []
    h = lines[0].split(',')
    return [dict(zip(h, l.split(','))) for l in lines[1:] if l]


def notify(title, body, high=False):
    if not TOPIC:
        return
    try:
        rq = urllib.request.Request('https://ntfy.sh/' + TOPIC, data=(title + '\n' + body).encode('utf-8'),
                                    headers={'Priority': 'high' if high else 'default'})
        urllib.request.urlopen(rq, timeout=15).read()
    except Exception as e:
        log('通知NG ' + repr(e))


class Web:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))

    def req(self, url, headers=None, data=None, timeout=20):
        h = {'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'}
        h.update(headers or {})
        rq = urllib.request.Request(url, data=data, headers=h)
        try:
            with self.op.open(rq, timeout=timeout) as r:
                b = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    b = gzip.decompress(b)
                return r.status, b.decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            return e.code, ''
        except Exception:
            return 0, ''


def num(s):
    try:
        return float(re.sub(r'[^\d.]', '', s))
    except Exception:
        return 0.0


def strategy_a(odds, p3, prm):
    """戦略A：予想締切オッズ = exp(W1*ln(今の単勝)+W2*ln(3連単換算)+C)。予想期待値 = p3*予想締切"""
    if p3 <= 0 or odds <= 0:
        return 9999.0, 0.0, 0.0, 0
    fo = 1.0 / p3
    pc = math.exp(prm['w1'] * math.log(odds) + prm['w2'] * math.log(fo) + prm['c'])
    ev = p3 * pc
    bands = prm.get('fo_bands')
    if bands:
        ok = any(lo < fo <= hi for lo, hi in bands)
    else:
        ok = fo <= prm['fomax']
    buy = int(ev >= prm['th'] and ok)
    return fo, pc, ev, buy


def strategy_b(od, p3, s1, R_, prm):
    """戦略B：締切で「期待値1.2以上・20倍以下」になりそうな確率を、締切前の流れから予想する"""
    act = list(od)
    if len(act) < 3:
        return {}
    c = prm['coef']
    fav = min(od.values())
    over = sum(1 / od[b] for b in act)
    rk = {b: i + 1 for i, b in enumerate(sorted(act, key=lambda b: (od[b], -p3[b])))}
    pr = {b: i + 1 for i, b in enumerate(sorted(act, key=lambda b: -p3[b]))}
    out = {}
    for b in act:
        o, p = od[b], p3[b]
        if o <= 0 or p <= 0:
            continue
        lo, lf = math.log(o), math.log(1 / p)
        o1, p1 = s1.get(b, (o, p))
        tr13 = math.log(o / o1) if o1 > 0 else 0.0
        p3tr = math.log(p / p1) if p1 > 0 else 0.0
        z = (c['intercept'] + c['lo3'] * lo + c['lfo'] * lf + c['lfo2'] * lf * lf + c['lgap'] * (lo - lf)
             + c['tr13'] * tr13 + c['p3tr'] * p3tr + c['rgap'] * (rk[b] - pr[b]) + c['R'] * R_
             + c['lfav'] * math.log(fav) + c['over'] * over + c.get(f'b{b}', 0))
        q = 1 / (1 + math.exp(-z))
        out[b] = (q, int(q >= prm['th'] and o <= prm.get('omax', 30)))
    return out


def git_save(msg):
    if os.environ.get('NO_GIT'):
        return
    with LOCK:
        try:
            subprocess.run(['git', 'add', 'data'], cwd=ROOT, check=False)
            r = subprocess.run(['git', 'commit', '-qm', msg], cwd=ROOT, capture_output=True, text=True)
            if 'nothing to commit' in (r.stdout + r.stderr):
                return
            for _ in range(3):
                subprocess.run(['git', 'pull', '-q', '--rebase', '-X', 'theirs', 'origin', 'main'], cwd=ROOT, check=False)
                if subprocess.run(['git', 'push', '-q', 'origin', 'HEAD:main'], cwd=ROOT).returncode == 0:
                    return
                time.sleep(5)
        except Exception as e:
            print('git NG', e)


# ======================= 競艇 =======================
KB = 'https://www.boatrace.jp/owpc/pc/race/'
KNAME = {'01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
         '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江', '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
         '17': '宮島', '18': '徳山', '19': '下関', '20': '若松', '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'}
KLOG_H = 'snap,time,jcd,R,deadline,boat,odds,p3,fo,pred,evA,buyA,votes,upd'
KCLS_H = 'jcd,R,boat,winner,payout,odds_close,p3_close,' + ','.join(f'odds{i},p3_{i},buyA{i}' for i in range(1, 6))


def k_deadlines(html):
    i = html.find('締切予定時刻')
    if i < 0:
        return []
    seg = html[i:i + 2500]
    return re.findall(r'<td class="[^"]*">\s*(\d{1,2}:\d\d)\s*</td>', seg)[:12]


def k_odds(html):
    ms = re.findall(r'is-boatColor(\d)">\d</td>.*?oddsPoint[^>]*>([^<]*)<', html, re.S)
    if len(ms) < 6:
        return None
    return {k + 1: num(ms[k][1]) for k in range(6)}


def k_odds3(html):
    ms = re.findall(r'oddsPoint[^>]*>([^<]*)<', html)
    if len(ms) != 120:
        return None
    inv = {b: 0.0 for b in range(1, 7)}
    for i, v in enumerate(ms):
        v = num(v)
        if v > 0:
            inv[i % 6 + 1] += 1 / v
    return inv


def k_upd(html):
    m = re.search(r'オッズ更新時間\s*(\d{1,2}:\d\d)', html)
    if m:
        return m.group(1)
    m = re.search(r'tab4_time">(.*?)</p>', html, re.S)
    if not m:
        m = re.search(r'(\d{1,2}:\d\d)\s*時点', html)
        return m.group(1) if m else ''
    return re.sub(r'[,\s]+', ' ', re.sub('<[^>]+>', ' ', m.group(1))).strip()


XS = [120, 80, 60, 30, 25, 12]   # 記録だけの細かいチェック（単勝のみ）


def k_points(html):
    return [re.sub(r'\s+', '', v) for v in re.findall(r'oddsPoint[^>]*>([^<]*)<', html)]


def k_split_boats(h):
    parts = re.split(r'is-boatColor(\d) is-fs14" rowspan="4">', h)
    o = {}
    for k in range(1, len(parts) - 1, 2):
        o.setdefault(int(parts[k]), parts[k + 1])
    return o


def k_info(jcd, R_, rl, bi):
    bl = k_split_boats(rl); bb = k_split_boats(bi)
    g = lambda p: (re.search(p, bi).group(1) if re.search(p, bi) else '')
    ws = g(r'風速</span>\s*<span class="weather1_bodyUnitLabelData">\s*(\d+)m')
    wv = g(r'波高</span>\s*<span class="weather1_bodyUnitLabelData">\s*(\d+)cm')
    wt = g(r'水温</span>\s*<span class="weather1_bodyUnitLabelData">\s*([\d.]+)')
    rows = []
    for b in range(1, 7):
        t = bl.get(b, '')
        m = re.search(r'\d{4}\s*/\s*<span class="[^"]*">\s*([AB][12])\s*</span>', t)
        L = re.findall(r'is-lineH2"\s+rowspan="4">\s*([^<]*)<br\s*/>\s*([^<]*)<br\s*/>\s*([^<]*)</td>', t)
        tm = re.search(r'<td rowspan="4">\s*(\d\.\d\d)\s*</td>', bb.get(b, ''))
        rows.append([jcd, R_, b, m.group(1) if m else '', num(L[1][0]) if len(L) > 1 else '', num(L[1][1]) if len(L) > 1 else '',
                     num(L[3][1]) if len(L) > 3 else '', tm.group(1) if tm else '', ws, wv, wt])
    return rows


def k_fine(w, x):
    q = f"?rno={x['R']}&jcd={x['jcd']}&hd={HD}"
    s1, h1 = w.req(KB + 'oddstf' + q)
    od = k_odds(h1) if s1 == 200 else None
    if od:
        append_csv('kyotei_fine.csv', 'time,jcd,R,deadline,upd,o1,o2,o3,o4,o5,o6',
                   [[f'{now():%H:%M:%S}', x['jcd'], x['R'], f"{x['dl']:%H:%M}", k_upd(h1)] + [od[b] for b in range(1, 7)]])


def k_result(html):
    m = re.search(r'単勝</td>.*?numberSet1_number[^>]*>(\d)</span>.*?is-payout1">&yen;([\d,]+)', html, re.S)
    return (int(m.group(1)), int(m.group(2).replace(',', ''))) if m else None


def p3_of(inv, act):
    s = sum(inv[b] for b in act)
    return {b: (inv[b] / s if s > 0 else 0.0) for b in act}


def kyotei_main():
    prm = CFG['kyotei_A']
    w = Web()
    st, idx = w.req(KB + 'index?hd=' + HD)
    jcds = sorted(set(re.findall(r'jcd=(\d\d)', idx)))
    races = []
    for j in jcds:
        st, h = w.req(f'{KB}racelist?rno=1&jcd={j}&hd={HD}')
        for r, t in enumerate(k_deadlines(h), 1):
            hh, mm = map(int, t.split(':'))
            dl = TODAY.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(hours=hh, minutes=mm)
            races.append({'jcd': j, 'R': r, 'dl': dl, 'snap': 0, 'st': 'wait'})
        time.sleep(0.3)
    done_snaps = {}
    s1map = {}
    for row in read_csv('kyotei_log.csv'):
        k = (row['jcd'], int(row['R']))
        done_snaps[k] = max(done_snaps.get(k, 0), int(row['snap']))
        if row['snap'] == '1':
            s1map.setdefault(k, {})[int(row['boat'])] = (float(row['odds']), float(row['p3']))
    for x in races:
        x['snap'] = done_snaps.get((x['jcd'], x['R']), 0)
        x['s1'] = s1map.get((x['jcd'], x['R']), {})
        if x['dl'] < now() + datetime.timedelta(seconds=10) or x['snap'] >= len(SN):
            x['st'] = 'past'
    left = sum(1 for x in races if x['st'] == 'wait')
    log(f'競艇: 開催{len(jcds)}場 / これから締切 {left}レース')
    debug_saved = os.path.exists(os.path.join(DDIR, 'kyotei_oddstf_sample.html'))
    pool = ThreadPoolExecutor(8)
    while time.time() - T0 < RUN_MIN * 60:
        n = now()
        busy = False
        for x in races:
            if x['st'] != 'wait':
                continue
            sec = (x['dl'] - n).total_seconds()
            if sec < 2:
                x['st'] = 'past'
                continue
            xi = x.setdefault('xi', 0)
            while xi < len(XS) and sec < XS[xi] - 8:
                xi += 1
            if xi < len(XS) and sec <= XS[xi]:
                pool.submit(k_fine, w, dict(x))
                xi += 1
            x['xi'] = xi
            if x['snap'] >= len(SN) or sec > SN[x['snap']]:
                if x['snap'] < len(SN) and sec - SN[x['snap']] < 7:
                    busy = True
                if xi < len(XS) and sec - XS[xi] < 7:
                    busy = True
                continue
            q = f"?rno={x['R']}&jcd={x['jcd']}&hd={HD}"
            f1 = pool.submit(w.req, KB + 'oddstf' + q)
            f2 = pool.submit(w.req, KB + 'odds3t' + q)
            f3 = pool.submit(w.req, KB + 'racelist' + q) if x['snap'] < 3 else None
            f4 = pool.submit(w.req, KB + 'odds2tf' + q)
            f6 = pool.submit(w.req, KB + 'oddsk' + q)
            f7 = pool.submit(w.req, KB + 'odds3f' + q)
            f5 = pool.submit(w.req, KB + 'beforeinfo' + q) if x['snap'] == 2 else None
            (s1, h1), (s2, h2) = f1.result(), f2.result()
            s4, h4 = f4.result()
            try:
                stamp = f'{now():%H:%M:%S}'
                rowsF = [[x['snap'] + 1, stamp, x['jcd'], x['R'], '3t', ' '.join(k_points(h2))]]
                if s4 == 200:
                    rowsF.append([x['snap'] + 1, stamp, x['jcd'], x['R'], '2tf', ' '.join(k_points(h4))])
                    if not os.path.exists(os.path.join(DDIR, 'kyotei_odds2tf_sample.html')):
                        open(os.path.join(DDIR, 'kyotei_odds2tf_sample.html'), 'w', encoding='utf-8').write(h4)
                if s1 == 200:
                    rowsF.append([x['snap'] + 1, stamp, x['jcd'], x['R'], 'tf', ' '.join(k_points(h1))])
                for kd, fx in [('k', f6), ('3f', f7)]:
                    sx, hx = fx.result()
                    if sx == 200:
                        rowsF.append([x['snap'] + 1, stamp, x['jcd'], x['R'], kd, ' '.join(k_points(hx))])
                        pth = os.path.join(DDIR, f'kyotei_odds{kd}_sample.html')
                        if not os.path.exists(pth):
                            open(pth, 'w', encoding='utf-8').write(hx)
                append_csv('kyotei_odds_full.csv', 'snap,time,jcd,R,kind,values', rowsF)
                if f5:
                    s5, h5 = f5.result()
                    s3x, h3x = f3.result()
                    if s5 == 200 and s3x == 200:
                        append_csv('kyotei_info.csv', 'jcd,R,boat,cls,nat,loc,mot,tenji,ws,wv,wtemp', k_info(x['jcd'], x['R'], h3x, h5))
            except Exception:
                log('追加記録NG ' + traceback.format_exc().splitlines()[-1])
            if f3:
                s3, h3 = f3.result()
                ts = k_deadlines(h3)
                if len(ts) >= x['R']:
                    hh, mm = map(int, ts[x['R'] - 1].split(':'))
                    nd = TODAY.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(hours=hh, minutes=mm)
                    if nd > x['dl']:
                        x['dl'] = nd
                        log(f"競艇 {KNAME[x['jcd']]}{x['R']}R 締切変更 → {nd:%H:%M}")
                        continue
            od = k_odds(h1) if s1 == 200 else None
            inv = k_odds3(h2) if s2 == 200 else None
            if not od or not inv:
                continue
            act = [b for b in range(1, 7) if od[b] > 0]
            if len(act) < 3:
                continue
            x['snap'] += 1
            p3 = p3_of(inv, act)
            prm = cfg()['kyotei_A']
            upd = k_upd(h1)
            if not debug_saved and x['snap'] >= 3:
                open(os.path.join(DDIR, 'kyotei_oddstf_sample.html'), 'w', encoding='utf-8').write(h1)
                debug_saved = True
            rows, buys = [], []
            for b in act:
                fo, pc, ev, by = strategy_a(od[b], p3[b], prm)
                rows.append([x['snap'], f'{now():%H:%M:%S}', x['jcd'], x['R'], f"{x['dl']:%H:%M}", b, od[b], f'{p3[b]:.4f}',
                             f'{fo:.2f}', f'{pc:.2f}', f'{ev:.3f}', by, '', upd.replace(',', ' ')])
                if by:
                    buys.append(f'{b}号艇 今{od[b]:.1f}倍→予想締切{pc:.1f}倍（予想期待値{ev:.2f}）')
            append_csv('kyotei_log.csv', KLOG_H, rows)
            if x['snap'] == 1:
                x['s1'] = {b: (od[b], p3[b]) for b in act}
            prmB = cfg().get('kyotei_B')
            resB = strategy_b({b: od[b] for b in act}, p3, x.get('s1', {}), x['R'], prmB) if prmB else {}
            buysB = [b for b in resB if resB[b][1]]
            if resB:
                append_csv('kyotei_B.csv', 'snap,time,jcd,R,boat,odds,qB,buyB',
                           [[x['snap'], f'{now():%H:%M:%S}', x['jcd'], x['R'], b, od[b], f'{resB[b][0]:.3f}', resB[b][1]] for b in resB])
            tag = f"{KNAME[x['jcd']]} {x['R']}R 締切{x['dl']:%H:%M}"
            lines = [f"[{now():%H:%M:%S}] 競艇 {tag}（{LAB[x['snap']]}）オッズ更新{upd or '?'}  【戦略A】{'買い目あり' if buys else '買い目なし'}"]
            for r_ in rows:
                mark = '  ← 買い' if r_[11] else ''
                lines.append(f"    {r_[5]}号艇 今{float(r_[6]):6.1f}倍  3連単換算{float(r_[8]):6.1f}倍  予想締切{float(r_[9]):6.1f}倍  予想期待値{float(r_[10]):.2f}{mark}")
            if resB:
                lines.append('    【戦略B】' + '  '.join(f"{b}号艇{resB[b][0]*100:.0f}%{'←買い' if resB[b][1] else ''}" for b in resB))
            print('\n'.join(lines), flush=True)
            if prmB and prmB.get('notify') and x['snap'] == 3:
                if buysB:
                    pool.submit(notify, '【B】★買い ' + tag, '\n'.join(f"{b}号艇 今{od[b]:.1f}倍（締切でお得になる確率 {resB[b][0]*100:.0f}%）" for b in buysB), True)
            if x['snap'] <= 3 and prm.get('notify', True):
                if buys and (x['snap'] == 3 or not prm.get('final_only', False)):
                    t = ('【A】★最終判定 買い ' if x['snap'] == 3 else '【A】買い候補 ') + tag + ('' if x['snap'] == 3 else f'（{LAB[x["snap"]]}）')
                    pool.submit(notify, t, '\n'.join(buys), x['snap'] == 3)
                    x['ntf'] = 1
                elif x['snap'] == 3 and x.get('ntf'):
                    pool.submit(notify, '【A】最終判定 見送り ' + tag, '直前で条件から外れたよ（買わない）')
            if x['snap'] >= len(SN):
                x['st'] = 'past'
        time.sleep(0.5 if busy else 3)
        if not any(x['st'] == 'wait' for x in races):
            break
    log('競艇: 監視おわり')


def kyotei_settle():
    """締切から8分以上たったレースの結果と締切オッズを取って、close ファイルに書く"""
    w = Web()
    logrows = read_csv('kyotei_log.csv')
    done = {(r['jcd'], r['R']) for r in read_csv('kyotei_close.csv')}
    byrace = {}
    for r in logrows:
        byrace.setdefault((r['jcd'], r['R']), []).append(r)
    for k, rs in byrace.items():
        if k in done:
            continue
        hh, mm = map(int, rs[0]['deadline'].split(':'))
        dl = TODAY.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(hours=hh, minutes=mm)
        if now() < dl + datetime.timedelta(minutes=8):
            continue
        q = f'?rno={k[1]}&jcd={k[0]}&hd={HD}'
        s, h = w.req(KB + 'raceresult' + q)
        res = k_result(h) if s == 200 else None
        if not res:
            if now() > dl + datetime.timedelta(minutes=90):
                res = (0, 0)  # 中止など
            else:
                continue
        s1, h1 = w.req(KB + 'oddstf' + q)
        s2, h2 = w.req(KB + 'odds3t' + q)
        s4, h4 = w.req(KB + 'odds2tf' + q)
        s6, h6 = w.req(KB + 'oddsk' + q)
        s7, h7 = w.req(KB + 'odds3f' + q)
        try:
            rowsF = [['close', f'{now():%H:%M:%S}', k[0], k[1], '3t', ' '.join(k_points(h2))]]
            if s4 == 200:
                rowsF.append(['close', f'{now():%H:%M:%S}', k[0], k[1], '2tf', ' '.join(k_points(h4))])
            if s1 == 200:
                rowsF.append(['close', f'{now():%H:%M:%S}', k[0], k[1], 'tf', ' '.join(k_points(h1))])
            if s6 == 200:
                rowsF.append(['close', f'{now():%H:%M:%S}', k[0], k[1], 'k', ' '.join(k_points(h6))])
            if s7 == 200:
                rowsF.append(['close', f'{now():%H:%M:%S}', k[0], k[1], '3f', ' '.join(k_points(h7))])
            append_csv('kyotei_odds_full.csv', 'snap,time,jcd,R,kind,values', rowsF)
        except Exception:
            pass
        od = k_odds(h1) or {}
        inv = k_odds3(h2)
        boats = sorted({int(r['boat']) for r in rs})
        p3c = p3_of(inv, boats) if inv else {}
        out = []
        for b in boats:
            snaps = {int(r['snap']): r for r in rs if int(r['boat']) == b}
            row = [k[0], k[1], b, res[0], res[1] if res[0] == b else 0, od.get(b, ''), f'{p3c[b]:.4f}' if b in p3c else '']
            for i in range(1, 6):
                r = snaps.get(i)
                row += [r['odds'], r['p3'], r['buyA']] if r else ['', '', '']
            out.append(row)
        append_csv('kyotei_close.csv', KCLS_H, out)
        ab = [r_[2] for r_ in out if r_[7 + 3 * 2 + 2] == '1']
        if ab:
            hit = res[0] in ab
            print(f"[{now():%H:%M:%S}] 結果 競艇 {KNAME.get(k[0], k[0])}{k[1]}R  1着{res[0]}号艇 単勝{res[1]}円  戦略Aの買い目{ab} → {'的中！' if hit else 'はずれ'}", flush=True)
        time.sleep(0.3)


# ======================= オート =======================
AB = 'https://autorace.jp'
APL = {2: '川口', 3: '伊勢崎', 4: '浜松', 5: '飯塚', 6: '山陽'}
ALOG_H = 'snap,time,pc,R,deadline,car,odds,p3,fo,pred,evA,buyA,votes,upd'
ACLS_H = 'pc,R,car,winner,payout,odds_close,p3_close,votes_close,' + ','.join(f'odds{i},p3_{i},buyA{i},votes{i}' for i in range(1, 6))


class Auto:
    def __init__(self):
        self.w = Web()
        self.tok = ''
        self.xs = ''
        self.tt = 0

    def token(self):
        s, pg = self.w.req(AB + '/race_info/RaceResult/kawaguchi/2026-10-18_1')
        m = re.search(r'<meta name="csrf-token" content="([^"]+)"', pg)
        self.tok = m.group(1) if m else ''
        for c in self.w.cj:
            if c.name == 'XSRF-TOKEN':
                self.xs = urllib.parse.unquote(c.value)
        self.tt = time.time()

    def H(self):
        return {'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-TOKEN': self.tok, 'X-XSRF-TOKEN': self.xs,
                'Content-Type': 'application/json', 'Accept': 'application/json', 'Referer': AB + '/race_info/'}

    def post(self, api, pc, rn):
        if time.time() - self.tt > 1800:
            self.token()
        for _ in range(2):
            s, t = self.w.req(AB + '/race_info/' + api, headers=self.H(),
                              data=json.dumps({'placeCode': pc, 'raceDate': YMD, 'raceNo': rn}).encode())
            if s in (401, 403, 419):
                self.token()
                continue
            if s == 200 and '"result":"Success"' in t:
                return json.loads(t)['body']
            return None
        return None

    def today(self):
        s, t = self.w.req(AB + '/race_info/XML/Hold/Today', headers=self.H())
        try:
            return json.loads(t)['body']['today']
        except Exception:
            return []


def to_time(s):
    m = re.search(r'(\d{1,2}):(\d\d)', str(s or ''))
    if not m:
        return None
    return TODAY.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(hours=int(m.group(1)), minutes=int(m.group(2)))


def a_calc(bd):
    od = {a: num(str(bd.get('tnsOddsList', {}).get(str(a), 0))) for a in range(1, 9)}
    act = [a for a in od if od[a] > 0]
    r3 = bd.get('rt3OddsList', {}) or {}
    inv = {}
    for a in act:
        s = 0.0
        for b in act:
            if b == a:
                continue
            for c in act:
                if c in (a, b):
                    continue
                try:
                    v = num(str(r3[str(a)][str(b)][str(c)]))
                except Exception:
                    v = 0
                if v > 0:
                    s += 1 / v
        inv[a] = s
    tot = sum(inv.values())
    p3 = {a: (inv[a] / tot if tot > 0 else 0.0) for a in act}
    si = bd.get('salesInfo', {}) or {}
    return od, act, p3, str((si.get('tns') or {}).get('salesCount', '')), str(si.get('updateDate', ''))


def auto_main():
    prm = CFG['auto_A']
    A = Auto()
    A.token()
    plist = [(int(t['placeCode']), max(1, int(t.get('nowRaceNo') or 1))) for t in A.today()] or [(p, 1) for p in range(2, 7)]
    races = []
    for pc, r0 in plist:
        inf = A.post('OtherRaceInfo', pc, r0)
        if not inf:
            continue
        fin = int(inf.get('finalRaceNo') or 12)
        for rn in range(r0, fin + 1):
            ri = inf if rn == r0 else A.post('OtherRaceInfo', pc, rn)
            dl = to_time(ri.get('telvoteTime')) if ri else None
            if dl and dl > now() + datetime.timedelta(seconds=10):
                races.append({'pc': pc, 'R': rn, 'dl': dl, 'snap': 0, 'st': 'wait'})
    done_snaps = {}
    for row in read_csv('auto_log.csv'):
        k = (int(row['pc']), int(row['R']))
        done_snaps[k] = max(done_snaps.get(k, 0), int(row['snap']))
    for x in races:
        x['snap'] = done_snaps.get((x['pc'], x['R']), 0)
        if x['snap'] >= len(SN):
            x['st'] = 'past'
    log(f"オート: 開催 {'・'.join(sorted({APL[x['pc']] for x in races}))} / これから締切 {len(races)}レース")
    while time.time() - T0 < RUN_MIN * 60:
        n = now()
        busy = False
        for x in races:
            if x['st'] != 'wait':
                continue
            sec = (x['dl'] - n).total_seconds()
            if sec < 2:
                x['st'] = 'past'
                continue
            if x['snap'] >= len(SN) or sec > SN[x['snap']]:
                if x['snap'] < len(SN) and sec - SN[x['snap']] < 7:
                    busy = True
                continue
            if x['snap'] < 3:
                ri = A.post('OtherRaceInfo', x['pc'], x['R'])
                nd = to_time(ri.get('telvoteTime')) if ri else None
                if nd and nd > x['dl']:
                    x['dl'] = nd
                    log(f"オート {APL[x['pc']]}{x['R']}R 締切変更 → {nd:%H:%M}")
                    continue
            bd = A.post('Odds', x['pc'], x['R'])
            if not bd:
                continue
            od, act, p3, votes, upd = a_calc(bd)
            if len(act) < 3:
                continue
            prm = cfg()['auto_A']
            x['snap'] += 1
            auto_save_full(x['snap'], x['pc'], x['R'], bd)
            rows, buys = [], []
            for a in act:
                fo, pc_, ev, by = strategy_a(od[a], p3[a], prm)
                rows.append([x['snap'], f'{now():%H:%M:%S}', x['pc'], x['R'], f"{x['dl']:%H:%M}", a, od[a], f'{p3[a]:.4f}',
                             f'{fo:.2f}', f'{pc_:.2f}', f'{ev:.3f}', by, votes, upd.replace(',', ' ')])
                if by:
                    buys.append(f'{a}号車 今{od[a]:.1f}倍→予想締切{pc_:.1f}倍（予想期待値{ev:.2f}）')
            append_csv('auto_log.csv', ALOG_H, rows)
            tag = f"{APL[x['pc']]} {x['R']}R 締切{x['dl']:%H:%M}"
            if x['snap'] <= 3 and prm.get('notify', False) and buys:
                notify(('【オートA】★最終判定 買い ' if x['snap'] == 3 else '【オートA】買い候補 ') + tag, '\n'.join(buys), x['snap'] == 3)
            if x['snap'] >= len(SN):
                x['st'] = 'past'
        time.sleep(0.5 if busy else 3)
        if not any(x['st'] == 'wait' for x in races):
            break
    log('オート: 監視おわり')


AKEYS = ['tnsOddsList', 'fnsOddsList', 'rtwOddsList', 'rfwOddsList', 'widOddsList', 'rt3OddsList', 'rf3OddsList', 'salesInfo']


def auto_save_full(snap, pc, R_, bd, extra=None):
    try:
        rec = {'snap': snap, 'time': f'{now():%H:%M:%S}', 'pc': pc, 'R': R_}
        rec.update({k: bd.get(k) for k in AKEYS})
        if extra:
            rec.update(extra)
        with LOCK:
            with open(os.path.join(DDIR, 'auto_odds_full.jsonl'), 'a', encoding='utf-8') as f:
                f.write(json.dumps(rec, ensure_ascii=False, separators=(',', ':')) + '\n')
    except Exception:
        pass


def auto_settle():
    A = Auto()
    A.token()
    logrows = read_csv('auto_log.csv')
    done = {(r['pc'], r['R']) for r in read_csv('auto_close.csv')}
    byrace = {}
    for r in logrows:
        byrace.setdefault((r['pc'], r['R']), []).append(r)
    for k, rs in byrace.items():
        if k in done:
            continue
        dl = to_time(rs[0]['deadline'])
        if now() < dl + datetime.timedelta(minutes=10):
            continue
        br = A.post('RaceResult', int(k[0]), int(k[1]))
        pays = {}
        if br:
            for y in ((br.get('refundInfo') or {}).get('tns') or {}).get('list') or []:
                if y.get('carNo') is not None:
                    pays[int(y['carNo'])] = int(y.get('refund') or 0)
        if not pays:
            if now() > dl + datetime.timedelta(minutes=90):
                pays = {0: 0}
            else:
                continue
        bc = A.post('Odds', int(k[0]), int(k[1]))
        if bc:
            auto_save_full('close', int(k[0]), int(k[1]), bc, {'refundInfo': (br or {}).get('refundInfo'),
                           'order': [[r_.get('order'), r_.get('carNo')] for r_ in ((br or {}).get('raceResult') or [])]})
        od, act, p3, votes, upd = a_calc(bc) if bc else ({}, [], {}, '', '')
        cars = sorted({int(r['car']) for r in rs})
        win = '|'.join(str(c) for c in sorted(pays))
        out = []
        for a in cars:
            snaps = {int(r['snap']): r for r in rs if int(r['car']) == a}
            row = [k[0], k[1], a, win, pays.get(a, 0), od.get(a, ''), f'{p3[a]:.4f}' if a in p3 else '', votes]
            for i in range(1, 6):
                r = snaps.get(i)
                row += [r['odds'], r['p3'], r['buyA'], r['votes']] if r else ['', '', '', '']
            out.append(row)
        append_csv('auto_close.csv', ACLS_H, out)


def write_status():
    def summ(rows, key, idcol):
        n = h = ret = 0
        lst = []
        for r_ in rows:
            if r_.get(key) == '1':
                n += 1
                p = int(float(r_.get('payout') or 0))
                ret += p
                h += 1 if p > 0 else 0
                lst.append((r_, p))
        return n, h, ret, lst
    L = [f'# 今日のまとめ（{YMD}）', '', f'最終更新：{now():%H:%M}（10分おきに更新）', '']
    kc = read_csv('kyotei_close.csv')
    nr = len({(r_['jcd'], r_['R']) for r_ in kc})
    L += ['## 競艇・戦略A', '', f'結果が出たレース：{nr}', '', '| 判定した時点 | 点数 | 的中 | 投資 | 払戻 | 回収率 |', '|---|---|---|---|---|---|']
    for i, nm in [(3, '40秒前（最終判定）'), (4, '15秒前'), (5, '5秒前')]:
        n, h, ret, _ = summ(kc, f'buyA{i}', 'boat')
        L.append(f'| {nm} | {n} | {h} | {n*100}円 | {ret}円 | {ret/max(1,n):.0f}% |')
    n, h, ret, lst = summ(kc, 'buyA3', 'boat')
    L += ['', '### 40秒前の買い目と結果', '', '| レース | 艇 | 40秒前 | 締切 | 結果 |', '|---|---|---|---|---|']
    for r_, p in lst[::-1]:
        L.append(f"| {KNAME.get(r_['jcd'].zfill(2), r_['jcd'])}{r_['R']}R | {r_['boat']}号艇 | {r_['odds3']}倍 | {r_['odds_close']}倍 | {'的中 '+str(p)+'円' if p else 'はずれ'} |")
    bl = [r_ for r_ in read_csv('kyotei_B.csv') if r_['snap'] == '3' and r_['buyB'] == '1']
    res = {}
    for r_ in kc:
        res[(r_['jcd'], r_['R'], r_['boat'])] = r_
    nB = hB = retB = 0
    rowsB = []
    for r_ in bl:
        c_ = res.get((r_['jcd'], r_['R'], r_['boat']))
        if not c_:
            continue
        p = int(float(c_.get('payout') or 0))
        nB += 1; retB += p; hB += 1 if p > 0 else 0
        rowsB.append((r_, c_, p))
    L = L[:4] + ['## 競艇・戦略B（通知している戦略）', '', '| 点数 | 的中 | 投資 | 払戻 | 回収率 |', '|---|---|---|---|---|',
                 f'| {nB} | {hB} | {nB*100}円 | {retB}円 | {retB/max(1,nB):.0f}% |', '', '| レース | 艇 | 40秒前 | 締切 | 確率 | 結果 |', '|---|---|---|---|---|---|'] + \
        [f"| {KNAME.get(r_['jcd'].zfill(2), r_['jcd'])}{r_['R']}R | {r_['boat']}号艇 | {r_['odds']}倍 | {c_['odds_close']}倍 | {float(r_['qB'])*100:.0f}% | {'的中 '+str(p)+'円' if p else 'はずれ'} |" for r_, c_, p in rowsB[::-1]] + [''] + L[4:]
    ac = read_csv('auto_close.csv')
    L += ['', '## オート（記録のみ）', '', f"結果が出たレース：{len({(r_['pc'], r_['R']) for r_ in ac})}"]
    n, h, ret, _ = summ(ac, 'buyA3', 'car')
    L.append(f'（参考）競艇と同じ式で判定した場合：{n}点 的中{h} 投資{n*100}円 払戻{ret}円 回収率{ret/max(1,n):.0f}%')
    txt = '\n'.join(L) + '\n'
    with LOCK:
        open(os.path.join(DDIR, 'まとめ.md'), 'w', encoding='utf-8').write(txt)
        open(os.path.join(ROOT, 'data', '今日のまとめ.md'), 'w', encoding='utf-8').write(txt)


def settle_loop(stop):
    last_git = time.time()
    while not stop.is_set():
        for f in (kyotei_settle, auto_settle):
            try:
                f()
            except Exception:
                log('結果取得NG ' + traceback.format_exc().splitlines()[-1])
        if time.time() - last_git > 10 * 60:
            try:
                write_status()
            except Exception:
                log('まとめNG ' + traceback.format_exc().splitlines()[-1])
            git_save(f'記録 {now():%m/%d %H:%M}')
            last_git = time.time()
        stop.wait(60)


def guard(fn):
    def run():
        try:
            fn()
        except Exception:
            log(fn.__name__ + ' NG\n' + traceback.format_exc())
    return run


if __name__ == '__main__':
    _n = now()
    if _n.hour >= 23 or _n.hour < 7 or (_n.hour == 7 and _n.minute < 30):
        # 夜中はレースがないので、朝7:30（またはこの回の時間切れ）まで待ってから終わる。終わったら次の回が予約される
        wake = _n.replace(hour=7, minute=30, second=0, microsecond=0)
        if _n.hour >= 23:
            wake += datetime.timedelta(days=1)
        sec = min((wake - _n).total_seconds(), RUN_MIN * 60)
        print(f'夜なので {sec/60:.0f}分 待機して終わる', flush=True)
        time.sleep(max(0, sec))
        raise SystemExit(0)
    log(f'開始（{RUN_MIN:.0f}分まで動く）')
    if os.environ.get('START_NOTIFY') == '1':
        notify('記録ツール 起動', f'{now():%H:%M} から記録を始めるよ')
    stop = threading.Event()
    th = [threading.Thread(target=guard(kyotei_main)), threading.Thread(target=guard(auto_main))]
    for t in th:
        t.start()
    st = threading.Thread(target=settle_loop, args=(stop,))
    st.start()
    for t in th:
        t.join()
    # 監視が終わっても、結果がそろうまで最大15分待つ（時間内なら）
    end = time.time() + 15 * 60
    while time.time() < end and time.time() - T0 < RUN_MIN * 60 + 10 * 60:
        time.sleep(60)
    stop.set()
    st.join()
    for f in (kyotei_settle, auto_settle):
        try:
            f()
        except Exception:
            pass
    try:
        write_status()
    except Exception:
        pass
    log('終了')
    git_save(f'記録 {now():%m/%d %H:%M}（終了）')
