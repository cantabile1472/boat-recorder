# 過去日のオートレース：出走表（OtherRaceInfo）・締切オッズ（Odds）・結果（RaceResult）を autorace.jp の API から取って
# data/auto/YYYYMMDD.jsonl.gz に保存する（1行 = 1レース）
#  使い方: python tools/backfill_auto.py 20261001 20261031   （開始日 終了日）
import sys, os, re, json, gzip, time, datetime, urllib.request, urllib.error, urllib.parse, http.cookiejar
from concurrent.futures import ThreadPoolExecutor
AB = 'https://autorace.jp'
os.makedirs('data/auto', exist_ok=True)


class Web:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))

    def req(self, url, headers=None, data=None, timeout=30):
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


class Auto:
    def __init__(self):
        self.w = Web(); self.tok = ''; self.xs = ''; self.tt = 0

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

    def post(self, api, pc, rn, ymd):
        if time.time() - self.tt > 1800:
            self.token()
        for _ in range(3):
            s, t = self.w.req(AB + '/race_info/' + api, headers=self.H(),
                              data=json.dumps({'placeCode': pc, 'raceDate': ymd, 'raceNo': rn}).encode())
            if s in (401, 403, 419):
                self.token(); continue
            if s == 200 and '"result":"Success"' in t:
                return json.loads(t)['body']
            if s == 200:
                return None
            time.sleep(2)
        return None


def one(args):
    A, ymd, pc, rn = args
    inf = A.post('OtherRaceInfo', pc, rn, ymd)
    if not inf:
        return None
    od = A.post('Odds', pc, rn, ymd)
    rs = A.post('RaceResult', pc, rn, ymd)
    return {'day': ymd, 'pc': pc, 'R': rn, 'info': inf, 'odds': od, 'result': rs}


if __name__ == '__main__':
    d0 = datetime.datetime.strptime(sys.argv[1], '%Y%m%d'); d1 = datetime.datetime.strptime(sys.argv[2], '%Y%m%d')
    A = Auto(); A.token()
    d = d0
    while d <= d1:
        ymd = d.strftime('%Y-%m-%d'); fn = f"data/auto/{d:%Y%m%d}.jsonl.gz"
        if not os.path.exists(fn):
            rows = []
            # まず各場の1Rで開催の有無を見る
            held = [pc for pc in range(2, 7) if A.post('OtherRaceInfo', pc, 1, ymd)]
            jobs = [(A, ymd, pc, rn) for pc in held for rn in range(1, 13)]
            with ThreadPoolExecutor(4) as ex:
                for r in ex.map(one, jobs):
                    if r:
                        rows.append(r)
            if rows:
                with gzip.open(fn, 'wt', encoding='utf-8') as f:
                    for r in rows:
                        f.write(json.dumps(r, ensure_ascii=False) + '\n')
            print(ymd, '開催', held, len(rows), 'レース', flush=True)
        d += datetime.timedelta(days=1)
