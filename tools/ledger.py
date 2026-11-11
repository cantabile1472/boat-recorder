# 出資記録：通知Gで「買った前提」の買い目を集めて、結果・払戻をつけ、data/ledger.csv に累計する
#  前提: 通知が出たものは全部 STAKE 円で買っている。買えなかったレースは data/ledger_skip.txt に「YYYYMMDD 競技 場 R」で書く
#  使い方: python tools/ledger.py YYYYMMDD   （結果は probe/ に取得済みのHTMLと auto_odds_full.jsonl から）
import sys, os, csv, json, re, glob
HD = sys.argv[1]; D = f'data/{HD}'; STAKE = 100
START = {'20261109': '12:33'}   # 出資を始めた時刻（その日のそれ以前の通知は対象外）
T0 = START.get(HD, '00:00')
G_END = '20261110 16:55'        # 競艇の戦略Gの通知を止めた時刻（これ以降は戦略Hの通知 h_notify.csv が対象）
NA_END = '20261111 12:20'       # 地方・オートの戦略Gの通知を止めた時刻（これ以降は対象外）
KNAME = {'01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
         '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島', '17': '宮島', '18': '徳山', '19': '下関', '20': '若松', '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'}
BJ = {'船橋': '19', '浦和': '18', '川崎': '21', '大井': '20', '園田': '27', '笠松': '23', '名古屋': '24', '水沢': '11', '盛岡': '10', '金沢': '22', '高知': '31', '佐賀': '32', '門別': '36', '姫路': '28'}


def picks():
    """その日の通知対象（競技, 場コード, 場名, R, 買い目, 判定時オッズ, ★）"""
    out = []
    if os.path.exists(f'{D}/g_log.csv'):
        seen = {}
        for r in csv.DictReader(open(f'{D}/g_log.csv', encoding='utf-8')):
            n = len([x for x in r['rules'].split(' / ') if x]); k = (r['jcd'], r['R'])
            if n >= 2 and int(r['snap']) == 3 and (k not in seen) and r['time'][:5] >= T0 and f"{HD} {r['time'][:5]}" < G_END:
                seen[k] = dict(r, n=n)
        for (j, R), r in seen.items():
            if r.get('weather') == '3':
                continue
            if r.get('odds') and float(r['odds']) and float(r['odds']) < 2.0 and HD >= '20261109':
                continue
            out.append(['競艇', j, r['place'], int(R), '単勝1', float(r['odds'] or 0), int(r['n'] >= 4)])
    if os.path.exists(f'{D}/h_notify.csv'):   # 戦略H（〜11/11朝: s70のEV0.85以上 / 11/11〜: レース内2番目の艇がEV0.75以上。40秒前・6号艇除外）
        for r in csv.DictReader(open(f'{D}/h_notify.csv', encoding='utf-8')):
            out.append(['競艇H', r['jcd'].zfill(2), r['place'], int(r['R']), f"単勝{r['boat']}", float(r['odds'] or 0), 0])
    if os.path.exists(f'{D}/hf_notify.csv'):   # 戦略H 複勝（f70のEV0.7以上・1号艇除外）
        for r in csv.DictReader(open(f'{D}/hf_notify.csv', encoding='utf-8')):
            out.append(['競艇H複勝', r['jcd'].zfill(2), r['place'], int(r['R']), f"複勝{r['boat']}", float(r['fuku_lo'] or 0), 0])
    if os.path.exists(f'{D}/g_nar_log.csv'):
        for r in csv.DictReader(open(f'{D}/g_nar_log.csv', encoding='utf-8')):
            if len([x for x in r['rules'].split(' / ') if x]) >= 2 and r['time'][:5] >= T0 and f"{HD} {r['time'][:5]}" < NA_END:
                out.append(['地方', BJ.get(r['place'], ''), r['place'], int(r['R']), f"単勝{r['num']}", float(r['tan'] or 0), int(len(r['rules'].split(' / ')) >= 3)])
    if os.path.exists(f'{D}/g_auto_log.csv'):
        H = ['snap', 'time', 'pc', 'place', 'R', 'deadline', 'odds', 'p3', 'votes', 'hit']
        for row in csv.reader(open(f'{D}/g_auto_log.csv', encoding='utf-8')):
            if len(row) == 10 and row[9] == '1' and row[0] != 'snap' and row[1][:5] >= T0 and f"{HD} {row[1][:5]}" < NA_END:
                r = dict(zip(H, row)); out.append(['オート', r['pc'], r['place'], int(r['R']), '単勝1', float(r['odds'] or 0), int(float(r['p3']) < 0.15)])
    skip = set()
    if os.path.exists('data/ledger_skip.txt'):
        for l in open('data/ledger_skip.txt', encoding='utf-8'):
            p = l.split()
            if len(p) >= 4 and p[0] == HD:
                skip.add((p[1], p[2], int(p[3])))
    return [p for p in out if (p[0], p[2], p[3]) not in skip]


def result_kyotei(jcd, R, html):
    j = html.find('>単勝<')
    if j < 0:
        return None
    seg = html[j:html.find('</tbody>', j)]
    num = re.search(r'numberSet1_number[^>]*>(\d)</span>', seg); pay = re.search(r'&yen;([\d,]+)', seg)
    return (int(num.group(1)), int(pay.group(1).replace(',', '')) if pay else 0) if num else None


def result_nar(html):
    i = html.find('newRefundTable')
    if i < 0:
        return None
    t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html[i:html.find('</section>', i)]))
    m = re.search(r'単勝 (\d+) ([\d,]+)円', t)
    return (int(m.group(1)), int(m.group(2).replace(',', ''))) if m else None


def result_auto(pc, R):
    p = f'{D}/auto_odds_full.jsonl'
    if not os.path.exists(p):
        return None
    for l in open(p, encoding='utf-8'):
        d = json.loads(l)
        if str(d['pc']) == str(pc) and int(d['R']) == int(R) and (d.get('refundInfo') or {}).get('tns'):
            x = d['refundInfo']['tns']['list'][0]; return (int(x['carNo']), int(x['refund']))
    return None


if __name__ == '__main__':
    P = picks()
    # probe/ に結果HTMLがある前提（probe_urls.txt の順に 00.html, 01.html ...）
    urls = [l.strip() for l in open('probe_urls.txt', encoding='utf-8') if l.strip()] if os.path.exists('probe_urls.txt') else []
    pages = {}
    for i, u in enumerate(urls):
        fn = f'probe/{i:02d}.html'
        if os.path.exists(fn):
            pages[u] = open(fn, encoding='utf-8', errors='replace').read()
    rows = []
    for sport, code, place, R, sel, odds, star in P:
        res = None
        if sport == '競艇':
            u = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={R}&jcd={code}&hd={HD}"
            if u in pages: res = result_kyotei(code, R, pages[u])
        elif sport == '競艇H複勝':   # 複勝の払戻は公開データ（boatracecsv の payouts）
            fp = f"/home/claude/boatracecsv/boatracecsv.github.io/data/results/payouts/{HD[:4]}/{HD[4:6]}/{HD[6:]}.csv"
            if os.path.exists(fp):
                for c in csv.DictReader(open(fp, encoding='utf-8')):
                    if int(c['レースコード'][8:10]) == int(code) and int(c['レースコード'][10:12]) == R:
                        want_ = int(sel.replace('複勝', '')); got = 0
                        for k_ in ('1', '2', '3'):
                            if (c.get(f'複勝_{k_}着_艇番') or '').strip() == str(want_):
                                got = int(float(c[f'複勝_{k_}着_払戻金'] or 0))
                        res = (want_ if got else 0, got)
        elif sport == '競艇H':   # 結果はレコーダーの kyotei_close.csv から（1着艇と単勝払戻）
            if os.path.exists(f'{D}/kyotei_close.csv'):
                for c in csv.DictReader(open(f'{D}/kyotei_close.csv', encoding='utf-8')):
                    if int(c['jcd']) == int(code) and int(c['R']) == R and c.get('winner'):
                        res = (int(c['winner']), int(float(c['payout'])) if int(c['boat']) == int(c['winner']) else 0)
                        if int(c['boat']) == int(c['winner']):
                            break
        elif sport == '地方':
            u = f"https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceMarkTable?k_raceDate={HD[:4]}%2F{HD[4:6]}%2F{HD[6:]}&k_raceNo={R}&k_babaCode={code}"
            if u in pages: res = result_nar(pages[u])
        else:
            res = result_auto(code, R)
        want = int(sel.replace('単勝', '').replace('複勝', ''))
        if res is None:
            win, pay = '', ''
        else:
            win = res[0]; pay = res[1] * STAKE // 100 if res[0] == want else 0
        rows.append([HD, sport, place, R, sel, odds, star, STAKE, win, pay])
    fn = 'data/ledger.csv'; new = not os.path.exists(fn)
    old = [r for r in csv.reader(open(fn, encoding='utf-8'))][1:] if not new else []
    old = [r for r in old if r[0] != HD]
    with open(fn, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f); w.writerow(['日付', '競技', '場', 'R', '買い目', '判定時オッズ', '★', '出資', '1着', '払戻'])
        w.writerows(old); w.writerows(rows)
    allr = old + rows
    def summ(rs):
        st = sum(int(r[7]) for r in rs); py = sum(int(r[9]) for r in rs if r[9] != ''); n = len(rs); h = sum(1 for r in rs if r[9] not in ('', '0', 0) and int(r[9]) > 0)
        return n, h, st, py
    print(f"# 出資記録 {HD}")
    for sp in ('競艇', '競艇H', '競艇H複勝', '地方', 'オート'):
        n, h, st, py = summ([r for r in rows if r[1] == sp])
        if n: print(f"{sp}: {n}件 的中{h} 出資{st:,}円 払戻{py:,}円 回収率{py/st*100:.0f}%")
    n, h, st, py = summ(rows); print(f"本日合計: {n}件 的中{h} 出資{st:,}円 払戻{py:,}円 収支{py-st:+,}円 回収率{py/st*100 if st else 0:.0f}%")
    n, h, st, py = summ([r for r in allr if r[0] >= '20261109']); print(f"累計（11/9〜）: {n}件 的中{h} 出資{st:,}円 払戻{py:,}円 収支{py-st:+,}円 回収率{py/st*100 if st else 0:.0f}%")
    miss = [r for r in rows if r[9] == '']
    if miss: print('結果未取得:', [(r[2], r[3]) for r in miss])
