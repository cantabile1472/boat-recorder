# 競輪の結果（払戻）を後から取る：data/日付/keirin_odds.jsonl に記録したレースのうち、結果がまだのものを
#  Kドリームスの結果ページから取って data/keirin_results/YYYYMMDD.jsonl に保存（1ページごとに1.5秒あける）
#  python tools/keirin_results.py 20261104 20261105 ...
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keirin_recorder as K
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def day(d):
    f = os.path.join(ROOT, 'data', d, 'keirin_odds.jsonl')
    if not os.path.exists(f):
        print(d, '記録なし'); return
    races, have = {}, set()
    for l in open(f, encoding='utf-8'):
        try:
            x = json.loads(l)
        except Exception:
            continue
        if x.get('snap') == 'result':
            have.add(x['id'])
        elif x.get('id') and x.get('v'):
            races[x['id']] = (x['v'], x.get('name'), x.get('R'))
    os.makedirs(os.path.join(ROOT, 'data', 'keirin_results'), exist_ok=True)
    out = os.path.join(ROOT, 'data', 'keirin_results', d + '.jsonl'); ok = 0
    with open(out, 'w', encoding='utf-8') as w:
        for rid, (v, nm, R) in sorted(races.items()):
            if rid in have:
                continue
            pay = K.parse_result(K.get(f'{K.B}{v}/racedetail/{rid}/?pageType=showResult'))
            if pay:
                ok += 1
                w.write(json.dumps({'id': rid, 'v': v, 'name': nm, 'R': R, 'pay': pay}, ensure_ascii=False) + '\n')
            time.sleep(1.5)
    print(d, f'{len(races)}レース（元から結果あり {len(have)}）→ 新たに {ok}レース')


if __name__ == '__main__':
    for d in sys.argv[1:]:
        day(d)
