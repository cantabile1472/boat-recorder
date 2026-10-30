import urllib.parse
import urllib.request, http.cookiejar, json, re, datetime, gzip, traceback
JST=datetime.timezone(datetime.timedelta(hours=9))
now=datetime.datetime.now(JST); hd=now.strftime('%Y%m%d'); ymd=now.strftime('%Y-%m-%d')
out=[f'実行時刻(JST) {now:%Y-%m-%d %H:%M:%S}']
cj=http.cookiejar.CookieJar(); op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
UA={'User-Agent':'Mozilla/5.0','Accept-Encoding':'gzip'}
def get(url,headers=None,data=None):
    h=dict(UA); h.update(headers or {})
    rq=urllib.request.Request(url,data=data,headers=h)
    with op.open(rq,timeout=30) as r:
        b=r.read()
        if r.headers.get('Content-Encoding')=='gzip': b=gzip.decompress(b)
        return r.status,b.decode('utf-8','replace')
try:
    st,t=get(f'https://www.boatrace.jp/owpc/pc/race/index?hd={hd}')
    out.append(f'競艇 開催一覧: {st} {len(t)}文字 場数={len(set(re.findall(r"jcd=(\\d\\d)",t)))}')
    j=(re.findall(r"jcd=(\d\d)",t) or ['01'])[0]
    st,t=get(f'https://www.boatrace.jp/owpc/pc/race/oddstf?rno=1&jcd={j}&hd={hd}')
    out.append(f'競艇 単勝ページ: {st} {len(t)}文字 oddsPoint={t.count("oddsPoint")}')
    m=re.search(r'tab4_time">(.*?)</p>',t,re.S); out.append('  更新時刻欄: '+(re.sub(r'\s+',' ',re.sub('<[^>]+>',' ',m.group(1))).strip() if m else 'なし'))
except Exception as e: out.append('競艇 NG: '+repr(e))
try:
    st,pg=get('https://autorace.jp/race_info/RaceResult/kawaguchi/2026-10-18_1')
    tok=re.search(r'<meta name="csrf-token" content="([^"]+)"',pg).group(1)
    xs=''
    for c in cj:
        if c.name=='XSRF-TOKEN': xs=urllib.parse.unquote(c.value)
    out.append(f'オート ページ: {st} token={len(tok)}')
    H={'X-Requested-With':'XMLHttpRequest','X-CSRF-TOKEN':tok,'X-XSRF-TOKEN':xs,'Content-Type':'application/json','Accept':'application/json'}
    st,t=get('https://autorace.jp/race_info/XML/Hold/Today',headers=H)
    out.append(f'オート 今日の開催: {st} {t[:200]}')
    st,t=get('https://autorace.jp/race_info/Odds',headers=H,data=json.dumps({'placeCode':5,'raceDate':'2026-10-18','raceNo':3}).encode())
    out.append(f'オート オッズ: {st} {len(t)}文字 {t[:60]}')
except Exception as e: out.append('オート NG: '+repr(e))
try:
    st,t=get('https://ntfy.sh/v1/health'); out.append(f'ntfy: {st} {t[:50]}')
except Exception as e: out.append('ntfy NG: '+repr(e))
open('test_result.txt','w',encoding='utf-8').write('\n'.join(out)+'\n'); print('\n'.join(out))
