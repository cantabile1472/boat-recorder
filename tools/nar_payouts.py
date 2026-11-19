# 地方競馬の払戻（全券種）を公式の成績ページ（RaceMarkTable）から取って data/nar_payouts/YYYYMMDD.csv に保存
#  列：bc（競馬場コード）,R,kind（単勝・複勝・枠連複・馬連複・馬連単・ワイド・三連複・三連単 など）,combo,pay（100円あたり）
#  レースの一覧は data/日付/nar_odds.jsonl（記録したレース）から作る
#  python tools/nar_payouts.py 20261101 20261102 ...
import os, re, sys, json, time, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'}


def all_pays(html):
    i = html.find('newRefundTable')
    if i < 0:
        return []
    j = html.find('</section>', i)
    seg = html[i:j if j > 0 else None]; kind = ''; out = []
    for t in re.finditer(r'<td class="title"[^>]*>\s*([^<]+?)\s*</td>|<td class="[^"]*">\s*([\d\s\-－→]+?)\s*</td>\s*<td class="refundMoney">\s*([\d,]+)円', seg):
        if t.group(1):
            kind = re.sub(r'\s+', '', t.group(1))
        else:
            n = re.findall(r'\d+', t.group(2))
            if n:
                out.append((kind, '-'.join(n), int(t.group(3).replace(',', ''))))
    return out


def get(u):
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception:
            time.sleep(3)
    return ''


def day(d):
    f = os.path.join(ROOT, 'data', d, 'nar_odds.jsonl')
    if not os.path.exists(f):
        print(d, '記録なし'); return
    races = sorted({(str(int(x['bc'])), int(x['R'])) for x in map(json.loads, open(f, encoding='utf-8'))}, key=lambda z: (int(z[0]), z[1]))
    os.makedirs(os.path.join(ROOT, 'data', 'nar_payouts'), exist_ok=True)
    out = os.path.join(ROOT, 'data', 'nar_payouts', d + '.csv'); ok = 0
    with open(out, 'w', encoding='utf-8') as w:
        w.write('bc,R,kind,combo,pay\n')
        for bc, R in races:
            h = get(f"https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceMarkTable?k_raceDate={d[:4]}%2F{d[4:6]}%2F{d[6:]}&k_raceNo={R}&k_babaCode={bc}")
            P = all_pays(h); ok += bool(P)
            for k, c, p in P:
                w.write(f'{bc},{R},{k},{c},{p}\n')
            time.sleep(1.5)   # 相手に負担をかけない間隔
    print(d, f'{len(races)}レース中 {ok}レースの払戻')


if __name__ == '__main__':
    for d in sys.argv[1:]:
        day(d)
