# 地方競馬の公式サイトの「今日のレース」とオッズのページを保存して、作りを調べる
import os, re, urllib.request, gzip
B = 'https://www.keiba.go.jp'
os.makedirs('data/nar_pilot', exist_ok=True)
def get(u):
    try:
        rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'})
        with urllib.request.urlopen(rq, timeout=30) as r:
            b = r.read()
            if r.headers.get('Content-Encoding') == 'gzip': b = gzip.decompress(b)
            return r.status, b.decode('utf-8', 'replace')
    except Exception as e:
        return 0, repr(e)
log = []
st, top = get(B + '/KeibaWeb/TodayRaceInfo/TodayRaceInfoTop')
open('data/nar_pilot/top.html', 'w', encoding='utf-8').write(top); log.append(f'top {st} {len(top)}')
links = sorted(set(re.findall(r'href="(/KeibaWeb/TodayRaceInfo/[^"]+)"', top)))
log += links[:80]
race = [l for l in links if 'RaceList' in l or 'DebaTable' in l or 'k_babaCode' in l][:1]
if race:
    st, rl = get(B + race[0].replace('&amp;', '&')); open('data/nar_pilot/racelist.html', 'w', encoding='utf-8').write(rl); log.append(f'racelist {st} {len(rl)} {race[0]}')
    l2 = sorted(set(re.findall(r'href="(/KeibaWeb/TodayRaceInfo/[^"]+)"', rl))); log += ['--- racelist links'] + l2[:120]
    odd = [l for l in l2 if 'Odds' in l or 'odds' in l]
    for i, l in enumerate(odd[:12]):
        st, h = get(B + l.replace('&amp;', '&')); fn = f'data/nar_pilot/odds_{i}.html'
        open(fn, 'w', encoding='utf-8').write(h); log.append(f'{fn} {st} {len(h)} {l}')
open('data/nar_pilot/log.txt', 'w', encoding='utf-8').write('\n'.join(log))
print('\n'.join(log[:40]))
