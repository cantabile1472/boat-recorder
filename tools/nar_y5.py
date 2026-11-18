# 戦略Y5（地方競馬版の戦略Y）：買い目の判定・賭け金（ハーフケリー）・資金・結果・Bluesky（地方用の別アカウント）
#  判定：締切1分前の3連単オッズから3連複の確率を出し、3連複オッズと掛けたEVが 1.0〜1.2・10〜50倍・1レース3点まで
#  賭け金：資金×ハーフケリー（100円単位で切り捨て、最低100円）。資金は10万円から結果で増減（data/y5_bank.json）
#  Bluesky：BSKY_NAR_HANDLE / BSKY_NAR_APP_PASSWORD があり、config の strategy_Y5.bsky が true のときだけ投稿
#  投稿に計算根拠・ケリー・EV・判定時刻のオッズは書かない
import os, re, csv, json, datetime, threading, urllib.request
JST = datetime.timezone(datetime.timedelta(hours=9))
now = lambda: datetime.datetime.now(JST)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = threading.Lock()
BANK_P = os.path.join(ROOT, 'data', 'y5_bank.json')
ID = os.environ.get('BSKY_NAR_HANDLE', '').strip(); PW = os.environ.get('BSKY_NAR_APP_PASSWORD', '').strip()
_S = {}


def cfg():
    try:
        return json.load(open(os.path.join(ROOT, 'config.json'), encoding='utf-8')).get('strategy_Y5', {}) or {}
    except Exception:
        return {}


def num(s):
    try:
        return float(str(s).replace(',', ''))
    except Exception:
        return 0.0


def key(c):
    return '-'.join(sorted(re.findall(r'\d+', c), key=int))


def pick(rec, lo=10, hi=50, ev_lo=1.0, ev_hi=1.2, nmax=3):
    """[(組, 今のオッズ, 確率, EV), ...]。条件に合う組が nmax 点を超えたら見送り（空）"""
    t3 = [(c, num(r[0])) for c, *r in rec.get('tri3') or [] if '-' in c and r and num(r[0]) > 0]
    tr = {}
    for c, *r in rec.get('tri') or []:
        if '-' in c and r and num(r[0]) > 0:
            tr[key(c)] = num(r[0])
    if not t3 or not tr:
        return []
    s = sum(1 / o for _, o in t3); qt = {}
    for c, o in t3:
        k = key(c); qt[k] = qt.get(k, 0) + (1 / o) / s
    P = [(c, o, qt.get(c, 0), qt.get(c, 0) * o) for c, o in tr.items() if lo < o <= hi and ev_lo <= qt.get(c, 0) * o < ev_hi]
    return sorted(P, key=lambda z: z[1]) if len(P) <= nmax else []


def stake(q, o, bank):
    f = max((q * o - 1) / (o - 1), 0) if o > 1 else 0
    return max(int(bank * f / 2 // 100) * 100, 100)


def bank(delta=None, note=''):
    with LOCK:
        try:
            b = json.load(open(BANK_P, encoding='utf-8'))
        except Exception:
            b = {'bank': int(cfg().get('bank0', 100000)), 'log': []}
        if delta is not None:
            b['bank'] = int(round(b['bank'] + delta)); b.setdefault('log', []).append([f'{now():%Y%m%d %H:%M}', note, int(round(delta)), b['bank']])
            b['log'] = b['log'][-500:]
            json.dump(b, open(BANK_P, 'w', encoding='utf-8'), ensure_ascii=False)
        return b['bank']


def rows(ddir, fn):
    p = os.path.join(ddir, fn)
    return list(csv.DictReader(open(p, encoding='utf-8'))) if os.path.exists(p) else []


def append(ddir, fn, head, rs):
    with LOCK:
        p = os.path.join(ddir, fn); new = not os.path.exists(p)
        with open(p, 'a', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            if new:
                w.writerow(head.split(','))
            w.writerows(rs)


# ---------------- Bluesky（地方用アカウント） ----------------
def bsky_on():
    return bool(ID and PW and cfg().get('bsky'))


def post(text, quote=None, image=None, alt=''):
    if not (ID and PW):
        return None
    def api(path, body, tok=None, raw=None):
        h = {'Content-Type': 'image/png' if raw is not None else 'application/json'}
        if tok:
            h['Authorization'] = 'Bearer ' + tok
        rq = urllib.request.Request('https://bsky.social/xrpc/' + path, data=raw if raw is not None else json.dumps(body).encode('utf-8'), headers=h)
        return json.loads(urllib.request.urlopen(rq, timeout=30).read() or b'{}')
    facets = []
    for m in re.finditer(r'#(\S+)', text):
        st = len(text[:m.start()].encode('utf-8')); en = st + len(m.group(0).encode('utf-8'))
        facets.append({'index': {'byteStart': st, 'byteEnd': en}, 'features': [{'$type': 'app.bsky.richtext.facet#tag', 'tag': m.group(1)}]})
    rec = {'$type': 'app.bsky.feed.post', 'text': text, 'createdAt': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z', 'langs': ['ja'], 'facets': facets}
    if quote:
        rec['embed'] = {'$type': 'app.bsky.embed.record', 'record': {'uri': quote[0], 'cid': quote[1]}}
    for attempt in range(2):
        try:
            if 'tok' not in _S or attempt:
                s_ = api('com.atproto.server.createSession', {'identifier': ID, 'password': PW})
                _S.update(tok=s_['accessJwt'], did=s_['did'])
            body = dict(rec)
            if image and os.path.exists(image):
                try:
                    blob = api('com.atproto.repo.uploadBlob', None, _S['tok'], raw=open(image, 'rb').read())['blob']
                    imgs = {'$type': 'app.bsky.embed.images', 'images': [{'image': blob, 'alt': alt or text, 'aspectRatio': {'width': 1200, 'height': 675}}]}
                    body['embed'] = ({'$type': 'app.bsky.embed.recordWithMedia', 'record': rec['embed'], 'media': imgs} if quote else imgs)
                except Exception:
                    if not attempt:
                        raise
            r_ = api('com.atproto.repo.createRecord', {'repo': _S['did'], 'collection': 'app.bsky.feed.post', 'record': body}, _S['tok'])
            return r_.get('uri'), r_.get('cid')
        except Exception as e:
            if attempt:
                print('地方Bluesky投稿NG', repr(e), flush=True)
    return None


# ---------------- 判定（締切1分前） ----------------
def judge(ddir, place, R, close, post_t, rec, notify, log):
    c = cfg()
    if not c.get('on', True):
        return
    P = pick(rec, hi=c.get('hi', 50), ev_hi=c.get('ev_hi', 1.2))
    W = pick(rec, hi=100, ev_hi=1.2)
    append(ddir, 'y5_log.csv', 'time,place,R,close,rule,combo,odds,ev', [[f'{now():%H:%M:%S}', place, R, close, t, cb, o, f'{ev:.3f}'] for t, L in (('Y5', P), ('Y5w', W)) for cb, o, q, ev in L])
    if not P:
        return
    bk = bank()
    B = [(cb, stake(q, o, bk), o) for cb, o, q, ev in P]
    append(ddir, 'y5_bets.csv', 'time,place,R,close,post,combo,stake,odds,bank', [[f'{now():%H:%M:%S}', place, R, close, post_t, cb, st, o, bk] for cb, st, o in B])
    log(f"【Y5】{place}{R}R " + ' / '.join(f'{cb} {st}円' for cb, st, _ in B))
    if c.get('notify', True):
        notify(f"地方 {place}{R}R 3連複 " + ' / '.join(f'{cb} {st:,}円' for cb, st, _ in B),
               f"確定（戦略Y5・1分前）締切{close}\n" + '\n'.join(f"{cb}　{st:,}円　今{o:.1f}倍" for cb, st, o in B) + f"\n資金 {bk:,}円")
    if bsky_on():
        r = post(f"{place}競馬 {R}R\n3連複 " + ' / '.join(f'{cb} {st:,}円' for cb, st, _ in B) + f"\n#地方競馬 #{place}競馬")
        if r and r[0]:
            append(ddir, 'y5_bsky_ref.csv', 'place,R,uri,cid', [[place, R, r[0], r[1]]])


# ---------------- 結果 ----------------
def trio_pay(html):
    """成績ページ（RaceMarkTable）から3連複の (組, 100円あたり払戻)。まだ無ければ None"""
    i = html.find('newRefundTable')
    if i < 0:
        return None
    seg = html[i:html.find('</section>', i) if html.find('</section>', i) > 0 else None]
    kind = ''
    for t in re.finditer(r'<td class="title"[^>]*>\s*([^<]+?)\s*</td>|<td class="[^"]*">\s*([\d\s\-－→]+?)\s*</td>\s*<td class="refundMoney">\s*([\d,]+)円', seg):
        if t.group(1):
            kind = t.group(1).strip()
        elif '連複' in kind and len(re.findall(r'\d+', t.group(2))) == 3:
            return key(t.group(2)), int(t.group(3).replace(',', ''))
    return None


def settle(ddir, get, babacode, ds, log):
    """締切から8分以上たった未精算のレースの結果を取って、資金を増減。的中なら投稿。全部精算済みなら True"""
    bets = rows(ddir, 'y5_bets.csv'); done = {(r['place'], r['R']) for r in rows(ddir, 'y5_result.csv')}
    todo = {}
    for r in bets:
        if (r['place'], r['R']) not in done:
            todo.setdefault((r['place'], r['R']), []).append(r)
    for (pl, R), rs in todo.items():
        t = now(); hh, mm = map(int, rs[0]['post'].split(':'))
        post_t = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if t < post_t + datetime.timedelta(minutes=6):
            continue
        bc = babacode.get(pl)
        h = get(f"https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceMarkTable?k_raceDate={ds}&k_raceNo={R}&k_babaCode={bc}") if bc else ''
        if h and not os.path.exists(os.path.join(ddir, 'nar_result_sample.html')):
            open(os.path.join(ddir, 'nar_result_sample.html'), 'w', encoding='utf-8').write(h)
        tr = trio_pay(h) if h else None
        if tr is None and t < post_t + datetime.timedelta(minutes=60):
            continue   # まだ確定していない（60分たっても取れなければ返還扱い）
        inv = sum(int(r['stake']) for r in rs)
        hit = [r for r in rs if tr and r['combo'] == tr[0]]
        st = int(hit[0]['stake']) if hit else 0
        ret = st * tr[1] // 100 if hit else (0 if tr else inv)
        append(ddir, 'y5_result.csv', 'place,R,n,trio,pay,hit,inv,ret', [[pl, R, len(rs), tr[0] if tr else '返還', tr[1] if hit else 0, int(bool(hit)), inv, ret]])
        bank(ret - inv, f'{pl}{R}R')
        log(f"【Y5結果】{pl}{R}R {tr[0] if tr else '返還'} 購入{inv}円 払戻{ret}円 資金{bank():,}円")
        if hit and bsky_on():
            ref = [r for r in rows(ddir, 'y5_bsky_ref.csv') if r['place'] == pl and r['R'] == R]
            img = None
            try:
                import bsky_images
                os.makedirs(os.path.join(ddir, 'bsky_img'), exist_ok=True)
                img = os.path.join(ddir, 'bsky_img', f'y5hit_{pl}_{R}.png')
                bsky_images.hit_card(f'{pl}競馬', R, tr[0], ret, out=img, stake=st, horse=True, foot='@' + ID)
            except Exception as e:
                log('Y5的中画像NG ' + repr(e)); img = None
            post(f"🎯的中🎯 {pl}競馬 {R}R\n3連複 {tr[0]}\n💰{st:,}円 → {ret:,}円\n#地方競馬 #{pl}競馬", (ref[0]['uri'], ref[0]['cid']) if ref else None,
                 image=img, alt=f'的中 {pl}競馬{R}R 3連複{tr[0]} {st:,}円→{ret:,}円')
    return all((r['place'], r['R']) in {(x['place'], x['R']) for x in rows(ddir, 'y5_result.csv')} for r in rows(ddir, 'y5_bets.csv'))


def summary(ddir, today, log):
    """その日の全レースが精算済みになったら、本日と投稿開始からの成績を1回だけ投稿"""
    flag = os.path.join(ddir, 'y5_summary_posted')
    if os.path.exists(flag) or not bsky_on():
        return
    start = str(cfg().get('bsky_start', '99999999'))
    base = os.path.dirname(ddir)
    def stat(days):
        n = h = inv = ret = 0
        for d in days:
            for r in rows(os.path.join(base, d), 'y5_result.csv'):
                n += int(r['n']); h += int(r['hit']); inv += int(r['inv']); ret += int(r['ret'])
        return n, h, inv, ret
    alld = sorted(d for d in os.listdir(base) if d.isdigit() and d >= start and d <= today and os.path.exists(os.path.join(base, d, 'y5_result.csv')))
    n1, h1, i1, r1 = stat([today])
    if n1 == 0 or not alld:
        open(flag, 'w').write('0'); return
    n2, h2, i2, r2 = stat(alld)
    lab = f"{int(today[4:6])}/{int(today[6:])}"
    txt = (f"{lab} の結果\n購入 {n1}点（{i1:,}円）・的中 {h1}本・回収率 {r1 / i1 * 100:.0f}%\n"
           f"投稿開始（{int(alld[0][4:6])}/{int(alld[0][6:])}）から\n購入 {n2}点（{i2:,}円）・的中 {h2}本・回収率 {r2 / i2 * 100:.0f}%\n#地方競馬")
    img = None
    try:
        import bsky_images
        days = [(f"{int(d[4:6])}/{int(d[6:])}",) + (lambda t: (t[2] / 100, t[3]))(stat([d])) for d in alld[-14:]]
        _, _, ib, rb = stat(alld[:-14]) if len(alld) > 14 else (0, 0, 0, 0)
        os.makedirs(os.path.join(ddir, 'bsky_img'), exist_ok=True)
        img = os.path.join(ddir, 'bsky_img', 'y5_summary.png')
        bsky_images.summary_card(lab, days, (n1, h1, round(r1 / i1 * 100)), (n2, h2, round(r2 / i2 * 100)), img, base=(ib / 100, rb), foot='@' + ID)
    except Exception as e:
        log('Y5成績画像NG ' + repr(e)); img = None
    post(txt, image=img, alt=txt.replace('\n', ' ')); open(flag, 'w').write(txt)
