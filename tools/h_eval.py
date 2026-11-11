# 戦略Hの答え合わせ：data/YYYYMMDD/h_log.csv（40秒前の全6艇の判定）× kyotei_close.csv（結果）
#  旧H＝全艇で s70のEV 0.85以上（6号艇除外）… 11/11 12:30〜 通知中
#  新H＝レース内で s70のEV が2番目の艇が 0.75以上（6号艇除外）… 記録のみで比較
#  python tools/h_eval.py [開始日YYYYMMDD]
import sys, glob, os
import pandas as pd
start = sys.argv[1] if len(sys.argv) > 1 else '20261111'
rows = []
for f in sorted(glob.glob('data/2026*/h_log.csv')):
    day = f.split('/')[1]
    c = f.replace('h_log', 'kyotei_close')
    if day < start or not os.path.exists(c):
        continue
    h = pd.read_csv(f).drop_duplicates(['jcd', 'R', 'boat'], keep='first')
    h = h[h.groupby(['jcd', 'R']).boat.transform('count') == 6]
    h['rk'] = h.groupby(['jcd', 'R']).s70_ev.rank(ascending=False, method='first')
    c = pd.read_csv(c)[['jcd', 'R', 'boat', 'winner', 'payout', 'odds_close']]
    h = h.merge(c, on=['jcd', 'R', 'boat'], how='left'); h['day'] = day
    h['pay'] = ((h.winner == h.boat) * h.payout).fillna(0)
    h['旧H'] = (h.s70_ev >= 0.85) & (h.boat != 6)
    h['新H'] = (h.rk == 2) & (h.s70_ev >= 0.75) & (h.boat != 6)
    rows.append(h[h['旧H'] | h['新H']])
if not rows:
    print('戦略H：まだ記録なし'); sys.exit()
P = pd.concat(rows); P.to_csv('data/h_picks.csv', index=False)
done = P[P.winner.notna()]
print(f'# 戦略H 答え合わせ {start}〜（40秒前判定・6号艇除外）')
for rule in ('旧H', '新H'):
    g = done[done[rule]]
    if g.empty:
        print(f'{rule}: なし'); continue
    for d, t in g.groupby('day'):
        print(f"  {rule} {d}: {len(t)}艇 的中{int((t.pay > 0).sum())} 出資{len(t)*100:,}円 払戻{int(t.pay.sum()):,}円 回収{t.pay.mean():.0f}%")
    print(f"{rule} 累計: {len(g)}艇 的中{int((g.pay > 0).sum())} 出資{len(g)*100:,}円 払戻{int(g.pay.sum()):,}円 収支{int(g.pay.sum()) - len(g)*100:+,}円 回収{g.pay.mean():.0f}%")
