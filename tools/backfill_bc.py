# ボートキャストの確定票数（単勝・複勝・ワイド・3連複 = hyousu1、3連単 = hyousu3）を過去日ぶん取る → data/bcvote/YYYYMMDD.csv.gz
import sys, os, time, gzip, csv, io, urllib.request, re
from concurrent.futures import ThreadPoolExecutor
B = 'https://race.boatcast.jp'
os.makedirs('data/bcvote', exist_ok=True)


def get(u):
    for _ in range(2):
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(rq, timeout=20) as r:
                return r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return ''
            time.sleep(1)
        except Exception:
            time.sleep(1)
    return ''


def one(args):
    hd, jo, rno = args
    h1 = get(f'{B}/txt/{jo}/bc_kakutei_hyousu1_{hd}_{jo}_{rno:02d}.txt')
    if not h1.startswith('data='):
        return None
    h3 = get(f'{B}/txt/{jo}/bc_kakutei_hyousu3_{hd}_{jo}_{rno:02d}.txt')
    return [jo, rno, h1.replace('\n', '|').replace('\t', ' '), h3.replace('\n', '|').replace('\t', ' ')]


for hd in sys.argv[1:]:
    fn = f'data/bcvote/{hd}.csv.gz'
    if os.path.exists(fn):
        continue
    lst = get(f'{B}/api_txt/getHoldingList2_{hd}.json')
    jos = sorted(set(re.findall(r'"RaceStudiumNo":"(\d\d)"', lst)))
    with ThreadPoolExecutor(8) as ex:
        rows = [x for x in ex.map(one, [(hd, jo, r) for jo in jos for r in range(1, 13)]) if x]
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(['jo', 'R', 'hyousu1', 'hyousu3']); w.writerows(rows)
    with gzip.open(fn, 'wt', encoding='utf-8') as f:
        f.write(buf.getvalue())
    print(hd, len(jos), '場', len(rows), 'レース', flush=True)
