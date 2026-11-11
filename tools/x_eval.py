# 試験中の戦略（記録のみ）の答え合わせ：オート
#  戦略X1＝オート単勝・a70のEV0.9以上・42秒前
#  戦略X2＝オート単勝・1号車・3連単換算の1着率5〜30%・a70のEV0.75以上・42秒前
#  data/YYYYMMDD/h_auto_log.csv（全車のa70のEV）× auto_close.csv（結果）
#  python tools/x_eval.py [開始日YYYYMMDD]
import sys, glob, os
import pandas as pd
start = sys.argv[1] if len(sys.argv) > 1 else '20261111'
rows = []
for f in sorted(glob.glob('data/2026*/h_auto_log.csv')):
    day = f.split('/')[1]
    c = f.replace('h_auto_log', 'auto_close')
    if day < start or not os.path.exists(c):
        continue
    h = pd.read_csv(f).drop_duplicates(['pc', 'R', 'car'], keep='first')
    cc = pd.read_csv(c)[['pc', 'R', 'car', 'winner', 'payout']].drop_duplicates(['pc', 'R', 'car'])
    h = h.merge(cc, on=['pc', 'R', 'car'], how='left'); h['day'] = day
    h['pay'] = ((h.winner == h.car) * h.payout).fillna(0); h['done'] = h.winner.notna()
    rows.append(h[h.s70_ev >= 0.9].assign(rule='戦略X1'))
    rows.append(h[(h.car == 1) & (h.p3 >= 0.05) & (h.p3 < 0.3) & (h.s70_ev >= 0.75)].assign(rule='戦略X2'))
if not rows:
    print('試験中の戦略：まだ記録なし'); sys.exit()
P = pd.concat(rows, ignore_index=True); P.to_csv('data/x_picks.csv', index=False)
done = P[P.done]
print(f'# 試験中の戦略（オート・記録のみ） {start}〜')
for rule, nm in (('戦略X1', 'a70のEV0.9以上'), ('戦略X2', '1号車・1着率5〜30%・a70のEV0.75以上')):
    g = done[done.rule == rule]
    if g.empty:
        print(f'{rule}（{nm}）: なし'); continue
    print(f"{rule}（{nm}） 累計: {len(g)}車 的中{int((g.pay > 0).sum())} 出資{len(g)*100:,}円 払戻{int(g.pay.sum()):,}円 回収{g.pay.mean():.0f}%")
