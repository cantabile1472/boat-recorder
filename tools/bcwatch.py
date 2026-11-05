# 調査用：ボートキャストの集計中オッズが締切前にどれくらいの頻度で更新されるか調べる（数レース分、5秒ごと）
import json, time, datetime, urllib.request, hashlib, os
JST = datetime.timezone(datetime.timedelta(hours=9)); now = lambda: datetime.datetime.now(JST)
B = 'https://race.boatcast.jp'
def get(u):
    try:
        rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(rq, timeout=15) as r:
            return r.read().decode('utf-8', 'replace'), r.headers.get('Last-Modified', '')
    except Exception as e:
        return '', repr(e)
hd = now().strftime('%Y%m%d')
lst = json.loads(get(f'{B}/api_txt/getHoldingList2_{hd}.json')[0])['return_info']
races = []
for s in lst:
    jo = s['RaceStudiumNo']
    for i, t in enumerate(s['DeadlineTimeAll']):
        if not (len(t) == 5 and t[2] == ':' and t[:2].isdigit()):
            continue
        dl = now().replace(hour=int(t[:2]), minute=int(t[3:]), second=0, microsecond=0)
        if dl > now() + datetime.timedelta(minutes=4):
            races.append((dl, jo, i + 1))
races.sort()
os.makedirs('probe', exist_ok=True)
out = open('probe/bcwatch.txt', 'a', encoding='utf-8')
n = int(os.environ.get('NRACE', '3'))
for dl, jo, rno in races[:n]:
    u1 = f'{B}/txt/{jo}/bc_smt_od1_{hd}_{jo}_{rno:02d}.txt'
    u3 = f'{B}/txt/{jo}/bc_smt_od3_{hd}_{jo}_{rno:02d}.txt'
    uo = f'https://www.boatrace.jp/owpc/pc/race/oddstf?rno={rno}&jcd={jo}&hd={hd}'
    while now() < dl - datetime.timedelta(seconds=240):
        time.sleep(2)
    last = None
    while now() < dl + datetime.timedelta(seconds=90):
        b1, lm1 = get(u1); b3, lm3 = get(u3); bo, _ = get(uo)
        import re
        upd = re.search(r'オッズ更新時間[^\d]*(\d{1,2}:\d{2})', re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', bo)))
        tan = b1.split('\n')[3] if b1.count('\n') >= 3 else ''
        tan_o = ' '.join(re.findall(r'oddsPoint[^>]*>\s*([\d.]+)\s*<', bo)[:6])
        h = hashlib.md5((b1 + b3).encode()).hexdigest()[:8]
        line = f"{now():%H:%M:%S} {jo}-{rno}R 締切{dl:%H:%M} 残り{int((dl-now()).total_seconds()):4d}s | BC更新={lm1[17:25]} 内容={h} 単勝={tan.strip()[:40]} | 公式更新={upd.group(1) if upd else '?'} 単勝={tan_o}"
        if h != last:
            out.write(line + '\n'); out.flush(); print(line, flush=True)
        last = h
        time.sleep(5)
    # 確定
    k, lm = get(f'{B}/txt/{jo}/bc_kakutei_od1_{hd}_{jo}_{rno:02d}.txt')
    out.write(f"{now():%H:%M:%S} {jo}-{rno}R 確定 更新={lm[17:25]} 単勝={(k.split(chr(10))[3] if k.count(chr(10))>=3 else '').strip()[:40]}\n"); out.flush()
