# JRA：netkeiba のオッズAPIから過去レースの全券種の締切オッズを取って data/jra/odds_YYYYMM.jsonl.gz に保存（1行=1レース）
#  使い方: python tools/jra_odds.py 2026 1 3   （年 開始月 終了月）… data/jra/YYYYMM.jsonl.gz のレースIDを使う
import sys, os, json, gzip, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36', 'Referer': 'https://race.netkeiba.com/'}
TYPES = {'1': 'tan_fuku', '4': 'umaren', '5': 'wide', '6': 'umatan', '7': 'sanfuku', '8': 'santan'}


def get(u):
    for _ in range(3):
        try:
            rq = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(rq, timeout=30) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception:
            time.sleep(3)
    return ''


def one(rid):
    out = {'id': rid}
    for t, nm in TYPES.items():
        s = get(f'https://race.netkeiba.com/api/api_get_jra_odds.html?race_id={rid}&type={t}&action=init')
        try:
            j = json.loads(s)
            if j.get('status') != 'result':
                return None
            d = j['data']; out['time'] = d.get('official_datetime')
            for k, v in d['odds'].items():
                out[k] = {c: x[0] for c, x in v.items()}   # 組 → オッズ（文字列）
        except Exception:
            return None
        time.sleep(0.2)
    return out


if __name__ == '__main__':
    Y, m0, m1 = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    for M in range(m0, m1 + 1):
        src = f'data/jra/{Y}{M:02d}.jsonl.gz'
        if not os.path.exists(src):
            continue
        ids = [json.loads(l)['id'] for l in gzip.open(src, 'rt', encoding='utf-8')]
        fn = f'data/jra/odds_{Y}{M:02d}.jsonl.gz'
        done = {json.loads(l)['id'] for l in gzip.open(fn, 'rt', encoding='utf-8')} if os.path.exists(fn) else set()
        todo = [i for i in ids if i not in done]
        print(Y, M, len(ids), 'レース 未取得', len(todo), flush=True)
        with ThreadPoolExecutor(3) as ex, gzip.open(fn, 'at', encoding='utf-8') as f:
            for k, r in enumerate(ex.map(one, todo)):
                if r:
                    f.write(json.dumps(r, ensure_ascii=False) + '\n')
                if k % 100 == 0:
                    print(k, flush=True)
