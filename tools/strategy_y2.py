# 戦略Y2（記録のみ）：戦略Yの改良版
#   ・3連単から3連複の確率を出す前に、3連単120通りのうち異常に票を集めている買い目（3-2-1の大口など）を本来の線まで戻す（strategy_y.fix_anom）
#     本来の線＝1着確率から作るハービル × その組の普段の差（models/anom_3t.json）。普段のブレの3倍を超えたら「異常」
#   ・そのうえでYと同じ条件（40秒前の3連複が10〜50倍・EV1.0〜1.2）で選び、1Rの買い目が4点以上のレースは除く（実運用と同じ3点まで）
#   ・3連単から見たその組の確率が200秒前→40秒前で2割以上落ちた組（log比 -0.2 以下）を除く
#  経緯：11/14に戦略X4として「急落除外＋3-2-1歪みレースの1-2-3除外」で開始 → 11/16に名前をY2に変更し、
#        1-2-3除外の代わりに、異常な票を集めた買い目すべてを補正する形にした。条件は11/16に固定、11/16以降が本当の検証
#  比較のため「Y（3点まで）」も並べて出す。条件はあとから変えないこと
#  python tools/strategy_y2.py [開始日]   … 既定は 20261116
import sys, os, pickle, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import strategy_y as Y

start = sys.argv[1] if len(sys.argv) > 1 else '20261116'
M = pickle.load(open(Y.MODEL, 'rb'))
K = ['day', 'jcd', 'R']


def picks(fix):
    X = Y.build(day_min=start, fix321=fix)
    if X.empty:
        return X
    X['qb'] = Y.sm(X[['lq', 'lw']].values @ M['w'], X.gid.values)
    X['ev'] = X.qb * X.o3 * np.exp(M['q80'].predict(X[M['F']]))
    P = X[(X.o3 > 10) & (X.o3 <= 50) & (X.ev >= 1.0) & (X.ev < 1.2)].copy()
    P['n'] = P.groupby(K).c.transform('count')
    P = P[P.n <= 3].copy()
    P['mom'] = np.log(P.q3 / P.q1)
    return P


Yb = picks(False)            # 比較用：今のY（3点まで）
P = picks(True)              # Y2：異常な票を補正した確率で選ぶ
if P.empty and Yb.empty:
    print('戦略Y2：まだ記録なし'); sys.exit()
P['ex'] = P.mom <= -0.2
P[K + ['c', 'o3', 'oc', 'qb', 'ev', 'mom', 'ex', 'pay']].round(4).to_csv(os.path.join(Y.ROOT, 'data', 'y2_picks.csv'), index=False)


def line(t):
    return f"{len(t)}点 的中{int((t.pay > 0).sum())} 出資{len(t)*100:,}円 払戻{int(t.pay.sum()):,}円 回収{t.pay.mean():.0f}%" if len(t) else '0点'


print(f'# 戦略Y2（記録のみ：異常な票を補正した確率で選ぶ・3点まで・急落除外） {start}〜')
for d in sorted(set(P.day) | set(Yb.day)):
    t = P[P.day == d]; y = Yb[Yb.day == d]
    print(f'  {d}: Y(3点まで) {line(y)} ／ Y2 {line(t[~t.ex])}（急落で除外{int(t.ex.sum())}点・的中{int((t[t.ex].pay > 0).sum())}）')
print(f'Y(3点まで) 累計: {line(Yb)}')
print(f'戦略Y2 累計: {line(P[~P.ex])}')
print(f'急落で除外した分 累計: {line(P[P.ex])}')
