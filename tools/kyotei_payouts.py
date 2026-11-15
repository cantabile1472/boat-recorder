# 競艇の払戻（全券種）を公式の結果ページから作る
#  公開データ（boatracecsv）が11/15から取れなくなったので、その代わり。
#  出力は boatracecsv と同じ形式：data/payouts/YYYY/MM/DD.csv（h_eval.py・strategy_y.py などがそのまま読める）
#  ・recorder.py の kyotei_settle が、結果ページを開いたときに row_from_html() で1行ずつ追記する
#  ・取りこぼした日の分は、GitHub Actions で  python tools/kyotei_payouts.py 20261115 [20261116 ...]  を回して作り直す
import os, re, sys, csv, time, datetime, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEAD = ['レースコード', 'レース日', 'レース場', 'レース回', '締切時刻', '取得日時', '単勝_艇番', '単勝_払戻金',
        '複勝_1着_艇番', '複勝_1着_払戻金', '複勝_2着_艇番', '複勝_2着_払戻金', '複勝_3着_艇番', '複勝_3着_払戻金',
        '2連単_組番', '2連単_払戻金', '2連単_人気', '2連複_組番', '2連複_払戻金', '2連複_人気',
        '拡連複_1-2着_組番', '拡連複_1-2着_払戻金', '拡連複_1-2着_人気', '拡連複_1-3着_組番', '拡連複_1-3着_払戻金', '拡連複_1-3着_人気',
        '拡連複_2-3着_組番', '拡連複_2-3着_払戻金', '拡連複_2-3着_人気', '3連単_組番', '3連単_払戻金', '3連単_人気',
        '3連複_組番', '3連複_払戻金', '3連複_人気']


def parse(html):
    """結果ページの払戻表 → {券種: [(組番, 払戻, 人気), ...]}（組番は '1-3-5' / '1=3=5' の公式表記）"""
    i = html.find('勝式</th>')
    if i < 0:
        return {}
    seg = html[i:html.find('</table>', i)]
    out = {}
    for body in re.findall(r'<tbody>(.*?)</tbody>', seg, re.S):
        m = re.search(r'<td rowspan="\d+">\s*([^<]+?)\s*</td>', body)
        if not m:
            continue
        kind = m.group(1).strip()
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', body, re.S):
            nums = re.findall(r'numberSet1_number[^>]*>(\d)</span>', tr)
            seps = re.findall(r'numberSet1_text">([-=])</span>', tr)
            pay = re.search(r'is-payout1">&yen;([\d,]+)', tr)
            if not nums or not pay:
                continue
            tds = re.findall(r'<td>\s*([\d]+)\s*</td>', tr)
            combo = nums[0] + ''.join(s + n for s, n in zip(seps, nums[1:]))
            out.setdefault(kind, []).append((combo, int(pay.group(1).replace(',', '')), tds[-1] if tds else ''))
    return out


def row_from_html(html, hd, jcd, rno, deadline=''):
    """boatracecsv と同じ並びの1行。払戻表が無ければ None"""
    p = parse(html)
    if not p:
        return None
    def g(kind, i):
        L = p.get(kind) or []
        return L[i] if i < len(L) else ('', '', '')
    r = [f'{hd}{int(jcd):02d}{int(rno):02d}', f'{hd[:4]}-{hd[4:6]}-{hd[6:]}', f'{int(jcd):02d}', f'{int(rno):02d}R', deadline,
         datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()]
    t = g('単勝', 0); r += [t[0], t[1]]
    for i in range(3):
        t = g('複勝', i); r += [t[0], t[1]]
    for kind in ('2連単', '2連複'):
        t = g(kind, 0); r += list(t)
    for i in range(3):
        t = g('拡連複', i); r += list(t)
    for kind in ('3連単', '3連複'):
        t = g(kind, 0); r += list(t)
    return r


def path(hd):
    return os.path.join(ROOT, 'data', 'payouts', hd[:4], hd[4:6], f'{hd[6:]}.csv')


def append(row, hd):
    p = path(hd); os.makedirs(os.path.dirname(p), exist_ok=True)
    have = set()
    if os.path.exists(p):
        have = {r['レースコード'] for r in csv.DictReader(open(p, encoding='utf-8'))}
    if row[0] in have:
        return
    new = not os.path.exists(p)
    with open(p, 'a', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        if new:
            w.writerow(HEAD)
        w.writerow(row)


def races_of(hd):
    """その日のレース一覧（記録済みの kyotei_close.csv / kyotei_log.csv から）"""
    s = {}
    for fn in ('kyotei_close.csv', 'kyotei_log.csv'):
        p = os.path.join(ROOT, 'data', hd, fn)
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding='utf-8')):
                s[(int(r['jcd']), int(r['R']))] = r.get('deadline', '')
    return s


if __name__ == '__main__':
    UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'}
    for hd in sys.argv[1:]:
        rs = races_of(hd); n = 0
        for (jcd, rno), dl in sorted(rs.items()):
            u = f'https://www.boatrace.jp/owpc/pc/race/raceresult?rno={rno}&jcd={jcd:02d}&hd={hd}'
            try:
                with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as f:
                    h = f.read().decode('utf-8', 'replace')
                row = row_from_html(h, hd, jcd, rno, dl)
                if row:
                    append(row, hd); n += 1
            except Exception as e:
                print('NG', hd, jcd, rno, repr(e), flush=True)
            time.sleep(1.5)
        print(hd, f'{n}/{len(rs)}レース', flush=True)
