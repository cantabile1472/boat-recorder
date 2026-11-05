# 調査用：URL一覧を取ってきて probe/ に保存する（ヘッダも記録）
import os, gzip, urllib.request
os.makedirs('probe', exist_ok=True)
for i, u in enumerate(open('probe_urls.txt', encoding='utf-8').read().split()):
    try:
        rq = urllib.request.Request(u, headers={'User-Agent': os.environ.get('UA', 'Mozilla/5.0'), 'Accept-Encoding': 'gzip', 'Accept-Language': 'ja'})
        with urllib.request.urlopen(rq, timeout=30) as r:
            b = r.read()
            if r.headers.get('Content-Encoding') == 'gzip': b = gzip.decompress(b)
            st = r.status; fu = r.geturl(); hd = f"LM={r.headers.get('Last-Modified')} ET={r.headers.get('ETag')} CT={r.headers.get('Content-Type')} Date={r.headers.get('Date')}"
    except Exception as e:
        b = repr(e).encode(); st = 'ERR'; fu = u; hd = ''
    open(f'probe/{i:02d}.html', 'wb').write(b)
    import time; time.sleep(float(os.environ.get('SLEEP','0')))
    print(i, st, len(b), u, '|', hd, flush=True)
