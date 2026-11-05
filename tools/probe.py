# 調査用：URL一覧を取ってきて probe/ に保存する
import sys, os, gzip, urllib.request, re
os.makedirs('probe', exist_ok=True)
for i, u in enumerate(open('probe_urls.txt', encoding='utf-8').read().split()):
    try:
        rq = urllib.request.Request(u, headers={'User-Agent': os.environ.get('UA', 'Mozilla/5.0'), 'Accept-Encoding': 'gzip', 'Accept-Language': 'ja'})
        with urllib.request.urlopen(rq, timeout=30) as r:
            b = r.read()
            if r.headers.get('Content-Encoding') == 'gzip': b = gzip.decompress(b)
            st = r.status; fu = r.geturl()
    except Exception as e:
        b = repr(e).encode(); st = 'ERR'; fu = u
    open(f'probe/{i:02d}.html', 'wb').write(b)
    print(i, st, len(b), u, '->', fu, flush=True)
