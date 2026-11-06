# 地方競馬：過去レースの出馬表（DebaTable）と競走成績（RaceMarkTable）を取って、馬ごとの情報を保存する（手順3）
#  使い方: python tools/nar_cards.py 2026 6   → data/nar/cards_202606.jsonl.gz（馬ごと1行）
import sys, os, re, io, gzip, json, time, urllib.request, glob
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
BABA = {'帯広ば': '3', '盛岡': '10', '水沢': '11', '浦和': '18', '船橋': '19', '大井': '20', '川崎': '21', '金沢': '22', '笠松': '23', '名古屋': '24', '園田': '27', '姫路': '28', '高知': '31', '佐賀': '32', '門別': '36'}
B = 'https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/'


def get(u):
    for _ in range(3):
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(rq, timeout=30) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception:
            time.sleep(2)
    return ''


def txt(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s.replace('&nbsp;', ' '))).strip()


def num(s):
    try:
        return float(str(s).replace(',', ''))
    except Exception:
        return None


def parse_mark(h):
    """競走成績ページ：レース情報と馬ごとの結果"""
    t = txt(h[:h.find('<table')] if '<table' in h else h)
    race = {}
    m = re.search(r'(ダート|芝)\s*(\d+)ｍ（(左|右|直)）', t)
    if m:
        race['surface'], race['dist'], race['turn'] = m.group(1), int(m.group(2)), m.group(3)
    m = re.search(r'天候：(\S+)\s+馬場：(\S+)', t); race['weather'], race['track'] = (m.group(1), m.group(2)) if m else ('', '')
    m = re.search(r'第(\d+)競走\s*競走成績\s*(.*?)(?:ダート|芝)', t); race['title'] = m.group(2).strip() if m else ''
    m = re.search(r'(サラブレッド系|アラブ系)\s*([^\s]+)\s*(定量|別定|馬齢|ハンデ)', t)
    if m:
        race['age_cond'], race['wt_cond'] = m.group(2), m.group(3)
    m = re.search(r'1着([\d,]+)円', t); race['prize1'] = int(m.group(1).replace(',', '')) if m else None
    horses = {}
    i = h.find('<table')
    for row in re.findall(r'<tr class="tBorder">(.*?)</tr>', h[i:], re.S):
        c = re.findall(r'<td class="([a-p])[^"]*">(.*?)</td>', row, re.S)
        d = {k: txt(v) for k, v in c}
        if 'c' not in d or not d['c'].isdigit():
            continue
        hn = int(d['c'])
        jk = d.get('h', ''); mk = re.match(r'([★▲△◇☆])', jk)
        sa = re.match(r'(牡|牝|セ)\s*(\d+)', d.get('f', ''))
        hw = re.match(r'(\d+)\s*\(([-+]?\d+)\)', d.get('j', ''))
        horses[hn] = {'fin_txt': d.get('a', ''), 'waku': num(d.get('b')), 'name': d.get('d', ''), 'belong': d.get('e', ''),
                      'sex': sa.group(1) if sa else '', 'age': int(sa.group(2)) if sa else None, 'wt': num(d.get('g')),
                      'jockey': re.sub(r'[★▲△◇☆]|（.*?）', '', jk).strip(), 'j_area': (re.search(r'（(.*?)）', jk) or [None, ''])[1], 'j_mark': mk.group(1) if mk else '',
                      'trainer': d.get('i', ''), 'hw': int(hw.group(1)) if hw else num(d.get('j')), 'hw_diff': int(hw.group(2)) if hw else None,
                      'time': d.get('k', ''), 'margin': d.get('l', ''), 'last3f': num(d.get('m')), 'corner': d.get('n', ''), 'pop': num(d.get('o')), 'odds': num(d.get('p'))}
    return race, horses


def parse_deba(h):
    """出馬表ページ：馬ごとの過去5走と通算成績"""
    out = {}
    blocks = re.split(r'<td rowspan="5" class="horseNum">', h)
    for b in blocks[1:]:
        m = re.match(r'\s*(\d+)\s*<', b)
        if not m:
            continue
        hn = int(m.group(1)); seg = b[:b.find('<tr class="tBorder">')] if '<tr class="tBorder">' in b else b
        d = {}
        a = re.search(r'全&nbsp;&nbsp;</td>\s*<td[^>]*>\s*(\d+)-\s*</td>\s*<td[^>]*>\s*(\d+)-\s*</td>\s*<td[^>]*>\s*(\d+)-\s*</td>\s*<td[^>]*>\s*(\d+)\s*</td>', seg)
        d['rec_all'] = [int(v) for v in a.groups()] if a else None
        a = re.search(r'場&nbsp;&nbsp;</td>\s*<td[^>]*>\s*(\d+)-\s*</td>\s*<td[^>]*>\s*(\d+)-\s*</td>\s*<td[^>]*>\s*(\d+)-\s*</td>\s*<td[^>]*>\s*(\d+)\s*</td>', seg)
        d['rec_here'] = [int(v) for v in a.groups()] if a else None
        a = re.search(r'距&nbsp;&nbsp;</td>\s*<td[^>]*>\s*(\d+)-\s*</td>\s*<td[^>]*>\s*(\d+)-\s*</td>\s*<td[^>]*>\s*(\d+)-\s*</td>\s*<td[^>]*>\s*(\d+)\s*</td>', seg)
        d['rec_dist'] = [int(v) for v in a.groups()] if a else None
        a = re.search(r'(\d\d)\.(\d\d)生', seg); d['birth'] = a.group(0) if a else ''
        past = []
        infos = re.findall(r'<div class="raceInfo">(.*?)</div>', seg, re.S)
        cls = re.findall(r'class="race">(.*?)<', seg)
        jk = re.findall(r'<td class="(?:rBorder)?">\s*(\d+)人\s*(\d+)\s*(\S+?)\s*([\d.]+)\s*</td>', seg)
        tm = re.findall(r'<td class="(?:rBorder)?">\s*(\d:\d\d\.\d)\s*([\d-]+)\s*([\d.]+)\s*</td>', seg)
        mg = re.findall(r'<td class="(?:rBorder)?">\s*(-?[\d.]+)\s+(\S+?)\s*</td>', seg)
        for k, inf in enumerate(infos):
            t = txt(inf)
            r = re.match(r'(\d+|取|中|除|失)\s*(\d\d\.\d\d\.\d\d)\s*(\S+)\s*(\d+)頭\s*(\S+)\s*(左|右|直)?(\d+)\s*(\d+)番', t)
            if not r:
                past.append(None); continue
            p = {'fin': int(r.group(1)) if r.group(1).isdigit() else r.group(1), 'date': r.group(2), 'track': r.group(3), 'nh': int(r.group(4)), 'place': r.group(5), 'dist': int(r.group(7)), 'num': int(r.group(8))}
            if k < len(cls): p['cls'] = txt(cls[k])
            if k < len(jk): p['pop'], p['hw'], p['jockey'], p['wt'] = int(jk[k][0]), int(jk[k][1]), re.sub(r'[★▲△◇☆]', '', jk[k][2]), float(jk[k][3])
            if k < len(tm): p['time'], p['corner'], p['last3f'] = tm[k][0], tm[k][1], float(tm[k][2])
            if k < len(mg): p['margin'] = float(mg[k][0])
            past.append(p)
        d['past'] = past
        out[hn] = d
    return out


def one(args):
    hd, bc, R_ = args
    q = f'?k_raceDate={hd[:4]}%2F{hd[4:6]}%2F{hd[6:]}&k_raceNo={R_}&k_babaCode={bc}'
    hm = get(B + 'RaceMarkTable' + q); hd_ = get(B + 'DebaTable' + q)
    if '馬番' not in hm:
        return []
    race, horses = parse_mark(hm)
    deba = parse_deba(hd_) if hd_ else {}
    rows = []
    for hn, v in horses.items():
        rec = {'day': hd, 'bc': bc, 'R': R_, 'num': hn}
        rec.update(race); rec.update(v); rec.update(deba.get(hn, {}))
        rows.append(rec)
    return rows


if __name__ == '__main__':
    Y, M = int(sys.argv[1]), int(sys.argv[2])
    p = pd.read_csv(f'data/nar/prob_{Y}{M:02d}.csv.gz')
    races = sorted({(str(d), BABA.get(b), int(r)) for b, d, r in zip(p['場'], p['日'], p['R']) if BABA.get(b)})
    print(Y, M, len(races), 'レース', flush=True)
    out = []
    with ThreadPoolExecutor(6) as ex:
        for k, rows in enumerate(ex.map(one, races)):
            out += rows
            if k % 200 == 0:
                print(k, len(out), flush=True)
    with gzip.open(f'data/nar/cards_{Y}{M:02d}.jsonl.gz', 'wt', encoding='utf-8') as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('保存', len(out), '頭', flush=True)
