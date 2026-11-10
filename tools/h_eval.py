# 戦略Hの答え合わせ：data/YYYYMMDD/h_log.csv（40秒前の判定）× kyotei_close.csv（結果）
#  python tools/h_eval.py [開始日YYYYMMDD]  → 日別と累計の件数・的中・回収率、data/h_picks.csv
import sys, glob, os
import pandas as pd
start = sys.argv[1] if len(sys.argv) > 1 else '20261110'
rows = []
for f in sorted(glob.glob('data/2026*/h_log.csv')):
    day = f.split('/')[1]
    if day < start:
        continue
    h = pd.read_csv(f); h = h[h.buy == 1].drop_duplicates(['jcd', 'R', 'boat'], keep='first')
    c = f.replace('h_log', 'kyotei_close')
    if h.empty or not os.path.exists(c):
        continue
    c = pd.read_csv(c)[['jcd', 'R', 'boat', 'winner', 'payout', 'odds_close']]
    h = h.merge(c, on=['jcd', 'R', 'boat'], how='left'); h['day'] = day
    h['pay'] = ((h.winner == h.boat) * h.payout).fillna(0)
    rows.append(h)
if not rows:
    print('戦略H：まだ記録なし'); sys.exit()
P = pd.concat(rows); P.to_csv('data/h_picks.csv', index=False)
done = P[P.winner.notna()]
print(f'# 戦略H（s70のEV0.85以上・40秒前・全艇）{start}〜')
for d, g in done.groupby('day'):
    print(f"{d}: {len(g)}艇 的中{int((g.pay > 0).sum())} 出資{len(g)*100:,}円 払戻{int(g.pay.sum()):,}円 回収{g.pay.mean():.0f}%")
print(f"累計: {len(done)}艇 的中{int((done.pay > 0).sum())} 出資{len(done)*100:,}円 払戻{int(done.pay.sum()):,}円 収支{int(done.pay.sum()) - len(done)*100:+,}円 回収{done.pay.mean():.0f}%")
if len(P) > len(done):
    print('結果未取得', len(P) - len(done), '艇')
