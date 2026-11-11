# 戦略Hの答え合わせ（40秒前判定）
#  戦略H 単勝＝s70のEV0.85以上・6号艇除外（h_log.csv） ／ 戦略H 複勝＝f70のEV0.7以上・1号艇除外（hf_log.csv）… 通知中
#  戦略H2＝レース内でs70のEVが2番目の艇が0.75以上・6号艇除外（h_log.csv から）… 記録のみ
#  単勝の結果は kyotei_close.csv、複勝の払戻は公開データ（boatracecsv の data/results/payouts）
#  python tools/h_eval.py [開始日YYYYMMDD]
import sys, glob, os
import pandas as pd
PUB = '/home/claude/boatracecsv/boatracecsv.github.io/data/results/payouts/'
start = sys.argv[1] if len(sys.argv) > 1 else '20261111'


def fuku_pay(day):
    f = f'{PUB}{day[:4]}/{day[4:6]}/{day[6:]}.csv'
    if not os.path.exists(f):
        return None
    p = pd.read_csv(f, dtype=str); out = {}
    for r in p.itertuples(index=False):
        r = r._asdict() if hasattr(r, '_asdict') else r
    for _, r in p.iterrows():
        j = int(r['レースコード'][8:10]); R = int(r['レースコード'][10:12])
        for c in ('1', '2', '3'):
            b = r.get(f'複勝_{c}着_艇番')
            if isinstance(b, str) and b.strip().isdigit():
                out[(j, R, int(b))] = float(str(r[f'複勝_{c}着_払戻金']).replace(',', '') or 0)
        out[(j, R, 'done')] = 1
    return out


rows = []
for f in sorted(glob.glob('data/2026*/h_log.csv')):
    day = f.split('/')[1]
    c = f.replace('h_log', 'kyotei_close')
    if day < start or not os.path.exists(c):
        continue
    h = pd.read_csv(f).drop_duplicates(['jcd', 'R', 'boat'], keep='first')
    h = h[h.groupby(['jcd', 'R']).boat.transform('count') == 6]
    h['rk'] = h.groupby(['jcd', 'R']).s70_ev.rank(ascending=False, method='first')
    cc = pd.read_csv(c)[['jcd', 'R', 'boat', 'winner', 'payout']]
    h = h.merge(cc, on=['jcd', 'R', 'boat'], how='left'); h['day'] = day
    h['pay'] = ((h.winner == h.boat) * h.payout).fillna(0); h['done'] = h.winner.notna()
    for rule, m in (('戦略H 単勝', (h.s70_ev >= 0.85) & (h.boat != 6)), ('戦略H2（記録のみ）', (h.rk == 2) & (h.s70_ev >= 0.75) & (h.boat != 6))):
        rows.append(h[m].assign(rule=rule))
for f in sorted(glob.glob('data/2026*/hf_log.csv')):
    day = f.split('/')[1]
    if day < start:
        continue
    fp = fuku_pay(day)
    if fp is None:
        continue
    h = pd.read_csv(f).drop_duplicates(['jcd', 'R', 'boat'], keep='first'); h = h[h.buy == 1]; h['day'] = day
    h['done'] = [(int(j), int(R), 'done') in fp for j, R in zip(h.jcd, h.R)]
    h['pay'] = [fp.get((int(j), int(R), int(b)), 0) for j, R, b in zip(h.jcd, h.R, h.boat)]
    rows.append(h.assign(rule='戦略H 複勝'))
if not rows:
    print('戦略H：まだ記録なし'); sys.exit()
P = pd.concat(rows, ignore_index=True); P.to_csv('data/h_picks.csv', index=False)
done = P[P.done]
print(f'# 戦略H 答え合わせ {start}〜（40秒前判定）')
for rule in ('戦略H 単勝', '戦略H 複勝', '戦略H2（記録のみ）'):
    g = done[done.rule == rule]
    if g.empty:
        print(f'{rule}: なし'); continue
    for d, t in g.groupby('day'):
        print(f"  {rule} {d}: {len(t)}点 的中{int((t.pay > 0).sum())} 出資{len(t)*100:,}円 払戻{int(t.pay.sum()):,}円 回収{t.pay.mean():.0f}%")
    print(f"{rule} 累計: {len(g)}点 的中{int((g.pay > 0).sum())} 出資{len(g)*100:,}円 払戻{int(g.pay.sum()):,}円 収支{int(g.pay.sum()) - len(g)*100:+,}円 回収{g.pay.mean():.0f}%")
