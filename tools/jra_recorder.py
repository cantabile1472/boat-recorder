# JRA：締切前オッズの記録（全券種：単勝・複勝・馬連・ワイド・馬単・3連複・3連単）
#  公開データベース用（分刻み）→ data/日付/jra_pub.jsonl ：朝一・60/30/15/10/5/3/2/1分前
#  自分たち専用（秒単位・確定）→ data/日付/jra_odds.jsonl ：40秒前・15秒前・確定（発走5分後）
#  締切は発走の2分前として数える。開催がない日は何もせず終わる
import os, re, json, time, datetime, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor
JST = datetime.timezone(datetime.timedelta(hours=9))
def now():
    return datetime.datetime.now(JST).replace(tzinfo=None)
RUN_MIN = float(os.environ.get('RUN_MINUTES', 330)); T0 = time.time()
TODAY = now(); HD = TODAY.strftime('%Y%m%d')
DDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', HD); os.makedirs(DDIR, exist_ok=True)
LOCK = threading.Lock()
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36', 'Referer': 'https://race.netkeiba.com/'}
TYPES = {'1': 'tan', '2': 'fuku', '4': 'umaren', '5': 'wide', '6': 'umatan', '7': 'sanfuku', '8': 'santan'}
PS = [(3600, '60分前'), (1800, '30分前'), (900, '15分前'), (600, '10分前'), (300, '5分前'), (180, '3分前'), (120, '2分前'), (60, '1分前')]
SN = [(42, '40秒前'), (17, '15秒前')]
PLACE = {'01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京', '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'}


def log(m):
    t = f'[{now():%H:%M:%S}] {m}'
    print(t, flush=True)
    with LOCK:
        open(os.path.join(DDIR, 'jra_run_log.txt'), 'a', encoding='utf-8').write(t + '\n')


def get(u):
    for _ in range(3):
        try:
            rq = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(rq, timeout=20) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception:
            time.sleep(2)
    return ''


def save(rec, fn):
    with LOCK:
        with open(os.path.join(DDIR, fn), 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(',', ':')) + '\n')


def races_today():
    h = get(f'https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={HD}')
    out = {}
    for li in re.findall(r'<li class="RaceList_DataItem[^"]*">(.*?)</li>', h, re.S):
        m = re.search(r'race_id=(\d{12})', li); t = re.search(r'RaceList_Itemtime">\s*(\d{1,2}):(\d{2})', li)
        if not (m and t) or m.group(1)[4:6] not in PLACE:
            continue
        rid = m.group(1); post = TODAY.replace(hour=int(t.group(1)), minute=int(t.group(2)), second=0, microsecond=0)
        out[rid] = {'id': rid, 'place': PLACE[rid[4:6]], 'R': int(rid[10:12]), 'post': post, 'dl': post - datetime.timedelta(minutes=2)}
    return sorted(out.values(), key=lambda x: x['post'])


def odds(rid):
    """全券種のオッズ。発売前などで取れなければ None"""
    out = {}
    for t in ('1', '4', '5', '6', '7', '8'):   # 1 で単勝と複勝の両方が返ってくる
        s = get(f'https://race.netkeiba.com/api/api_get_jra_odds.html?race_id={rid}&type={t}&action=init')
        try:
            j = json.loads(s)
            if j.get('status') != 'result':
                if t == '1':
                    return None
                continue
            d = j['data']; out['official'] = d.get('official_datetime')
            for k, v in d['odds'].items():
                out[TYPES.get(k, k)] = {c: x[0] if isinstance(x, list) else x for c, x in v.items()}
        except Exception:
            if t == '1':
                return None
        time.sleep(0.15)
    return out


def snap(x, label, fn):
    try:
        o = odds(x['id'])
        if not o:
            return
        rec = {'label': label, 'sec': int((x['dl'] - now()).total_seconds()), 'time': f'{now():%H:%M:%S}', 'id': x['id'], 'place': x['place'], 'R': x['R'],
               'post': f"{x['post']:%H:%M}", 'deadline': f"{x['dl']:%H:%M}"}
        rec.update(o); save(rec, fn)
    except Exception as e:
        log(f"記録NG {x.get('place')}{x.get('R')}R {label} {e!r}")


def done_labels(fn):
    p = os.path.join(DDIR, fn); s = set()
    if os.path.exists(p):
        for l in open(p, encoding='utf-8'):
            try:
                d = json.loads(l); s.add((d['id'], d['label']))
            except Exception:
                pass
    return s


def main():
    rs = races_today()
    if not rs:
        log('JRA：今日は開催なし'); return
    pd_ = done_labels('jra_pub.jsonl') | done_labels('jra_odds.jsonl')
    for x in rs:
        x['done'] = {lb for (i, lb) in pd_ if i == x['id']}
    morning = [x for x in rs if not x['done'] and (x['dl'] - now()).total_seconds() > 3700]
    for x in morning:
        x['done'].add('朝一')
    log(f"JRA：開催 {', '.join(sorted({x['place'] for x in rs}))} / {len(rs)}レース（朝一 {len(morning)}）")
    pool = ThreadPoolExecutor(4)
    while time.time() - T0 < RUN_MIN * 60 and any('確定' not in x['done'] for x in rs):
        if morning:
            pool.submit(snap, dict(morning.pop(0)), '朝一', 'jra_pub.jsonl')
        for x in rs:
            sec = (x['dl'] - now()).total_seconds()
            for ps, lb in PS:
                if lb not in x['done'] and ps - 25 < sec <= ps:
                    x['done'].add(lb); pool.submit(snap, dict(x), lb, 'jra_pub.jsonl')
                elif lb not in x['done'] and sec <= ps - 25:
                    x['done'].add(lb)
            for ps, lb in SN:
                if lb not in x['done'] and ps - 10 < sec <= ps:
                    x['done'].add(lb); pool.submit(snap, dict(x), lb, 'jra_odds.jsonl')
                elif lb not in x['done'] and sec <= ps - 10:
                    x['done'].add(lb)
            if '確定' not in x['done'] and now() >= x['post'] + datetime.timedelta(minutes=5):
                x['done'].add('確定'); pool.submit(snap, dict(x), '確定', 'jra_odds.jsonl')
        time.sleep(2)
    pool.shutdown(wait=True)
    log('JRA：監視おわり')


if __name__ == '__main__':
    main()
