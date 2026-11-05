# 戦略Eの答え合わせ：e_picks.csv の買い目に結果と払戻をつけて回収率を出す
# 使い方: python tools/eval_e.py YYYYMMDD
import sys, os, re, csv, json, time, gzip, urllib.request
from concurrent.futures import ThreadPoolExecutor
HD = sys.argv[1]; D = f'data/{HD}'
ALL = len(sys.argv) > 2 and sys.argv[2] == 'all'   # all のときは買い目以外の全候補も答え合わせ
SRC, OUT = ('e_all.csv', 'e_eval_all') if ALL else ('e_picks.csv', 'e_eval')
KNAME = {'01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
         '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江', '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
         '17': '宮島', '18': '徳山', '19': '下関', '20': '若松', '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'}
KJ = {v: k for k, v in KNAME.items()}
APL = {2: '川口', 3: '伊勢崎', 4: '浜松', 5: '飯塚', 6: '山陽'}
BABA = {'3': '帯広', '10': '盛岡', '11': '水沢', '18': '浦和', '19': '船橋', '20': '大井', '21': '川崎', '22': '金沢', '23': '笠松', '24': '名古屋', '27': '園田', '28': '姫路', '31': '高知', '32': '佐賀', '36': '門別'}
BJ = {v: k for k, v in BABA.items()}


def get(u):
    for _ in range(3):
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'})
            with urllib.request.urlopen(rq, timeout=20) as r:
                b = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    b = gzip.decompress(b)
                return b.decode('utf-8', 'replace')
        except Exception:
            time.sleep(2)
    return ''


def key(sel):
    return '-'.join(sorted(re.split(r'[-=]', sel), key=int)) if re.search(r'[-=]', sel) else sel


def kyotei_pay(j, r):
    """{('複勝','3'):円, ('ワイド','1-3'):円}。結果がまだなら None"""
    h = get(f'https://www.boatrace.jp/owpc/pc/race/raceresult?rno={r}&jcd={j}&hd={HD}')
    out = {}
    for nm, kd in [('拡連複', 'ワイド'), ('複勝', '複勝')]:
        i = h.find('>' + nm + '<')
        if i < 0:
            continue
        seg = h[i: h.find('</tbody>', i)]
        for row in re.split(r'<tr', seg):
            nums = re.findall(r'numberSet1_number[^>]*>(\d)</span>', row)
            pay = re.search(r'&yen;([\d,]+)', row)
            if nums and pay:
                out[(kd, key('-'.join(nums)))] = int(pay.group(1).replace(',', ''))
    return out or None


def nar_pay(bc, r):
    """地方競馬：成績ページの払戻 {('複勝','5'):円, ('ワイド','4-5'):円}"""
    h = get(f'https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceMarkTable?k_raceDate={HD[:4]}%2F{HD[4:6]}%2F{HD[6:]}&k_raceNo={r}&k_babaCode={bc}')
    i = h.find('newRefundTable')
    if i < 0:
        return None
    seg = h[i:h.find('</section>', i)]
    out, kind = {}, ''
    for t in re.finditer(r'<td class="title"[^>]*>\s*([^<]+?)\s*</td>|<td class="[ad]">\s*([^<]+?)\s*</td>\s*<td class="refundMoney">\s*([\d,]+)円', seg):
        if t.group(1):
            kind = t.group(1)
        elif kind in ('複勝', 'ワイド'):
            out[(kind, key(t.group(2)))] = int(t.group(3).replace(',', ''))
    return out or None


def auto_pay():
    res = {}
    p = f'{D}/auto_odds_full.jsonl'
    if not os.path.exists(p):
        return res
    for l in open(p, encoding='utf-8'):
        d = json.loads(l)
        ri = d.get('refundInfo')
        if not ri:
            continue
        o = {}
        for x in (ri.get('fns') or {}).get('list', []):
            o[('複勝', str(x['carNo']))] = int(x.get('refund') or 0)
        for x in (ri.get('wid') or {}).get('list', []):
            o[('ワイド', key(f"{x['1thCarNo']}-{x['2thCarNo']}"))] = int(x.get('refund') or 0)
        res[(APL.get(int(d['pc']), str(d['pc'])), int(d['R']))] = o
    return res


def keirin_pay():
    res = {}
    p = f'{D}/keirin_odds.jsonl'
    if not os.path.exists(p):
        return res
    for l in open(p, encoding='utf-8'):
        d = json.loads(l)
        if d.get('snap') == 'result':
            res[(d['name'], int(d['R']))] = {('ワイド', key(s)): y for k, s, y in d['pay'] if k == 'ワイド'}
    return res


rows = list(csv.DictReader(open(f'{D}/{SRC}', encoding='utf-8')))
kt = sorted({(KJ[r['place']], int(r['R'])) for r in rows if r['sport'].startswith('競艇') and r['place'] in KJ})
with ThreadPoolExecutor(6) as ex:
    KP = dict(zip(kt, ex.map(lambda x: kyotei_pay(*x), kt)))
AP, CP = auto_pay(), keirin_pay()
nt = sorted({(BJ[r['place']], int(r['R'])) for r in rows if r['sport'].startswith('地方') and r['place'] in BJ})
with ThreadPoolExecutor(4) as ex:
    NP = dict(zip(nt, ex.map(lambda x: nar_pay(*x), nt)))
out = []
for r in rows:
    sp, snap = r['sport'][:-1], r['sport'][-1]
    R = int(r['R'])
    if sp == '競艇':
        pays = KP.get((KJ.get(r['place']), R))
    elif sp == 'オート':
        pays = AP.get((r['place'], R))
    elif sp == '競輪':
        pays = CP.get((r['place'], R))
    elif sp == '地方':
        pays = NP.get((BJ.get(r['place']), R))
    else:
        pays = None
    if pays is None:
        continue
    pay = pays.get((r['kind'], key(r['sel'])), 0)
    out.append(dict(r, sp=sp, snap=snap, pay=pay))
with open(f'{D}/{OUT}.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()) if out else ['sp'])
    w.writeheader(); w.writerows(out)
L = [f'# 戦略E 答え合わせ（{HD}）', '', '1点100円で全部買ったとして計算。「1分前判定」が通知と同じ条件。', '',
     '| 判定 | 競技 | 券種 | 点数 | 的中 | 的中率 | 回収率 |', '|---|---|---|---|---|---|---|']
lab = {'2': '2分前前後', '3': '1分前（通知）'}
for snap in ('3', '2'):
    for sp in ('競艇', 'オート', '競輪', '地方', '全部'):
        for kd in ('複勝', 'ワイド', '計'):
            g = [x for x in out if x['snap'] == snap and (sp == '全部' or x['sp'] == sp) and (kd == '計' or x['kind'] == kd)]
            if not g:
                continue
            n = len(g); hit = sum(1 for x in g if x['pay'] > 0); ret = sum(x['pay'] for x in g)
            L.append(f'| {lab[snap]} | {sp} | {kd} | {n} | {hit} | {hit/n*100:.0f}% | {ret/n:.0f}% |')
L += ['', '## 的中した買い目（1分前判定）：判定時の下限オッズ → 実際の払戻', '']
for x in out:
    if x['snap'] == '3' and x['pay'] > 0:
        L.append(f"- {x['sp']} {x['place']}{x['R']}R {x['kind']} {x['sel']}：{float(x['lo']):.1f}〜{float(x['hi']):.1f}倍 → {x['pay']/100:.1f}倍（確率{float(x['p'])*100:.0f}%）")
if not ALL:
    open(f'{D}/e_eval.md', 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))
print(OUT, len(out))
