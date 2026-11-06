# トリプル馬単の買い目：3レースの3連単オッズ（Odds3LenTan のHTML）から馬単の確率を出し、
# 3レースの的中確率の積が最大になるように N 組を配分する
#  使い方: python tools/triple.py N 10R.html 11R.html 12R.html
import sys, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nar_recorder import rank_table, tanfuku


def umatan_probs(h):
    """3連単オッズ → 馬単(1着,2着)の確率（3着を全部足す）"""
    tri = {}
    for r in rank_table(h):
        if r[0].count('-') == 2:
            v = float(r[1])
            if v > 0:
                tri[tuple(map(int, r[0].split('-')))] = 1 / v
    s = sum(tri.values())
    um = {}
    for (a, b, c), v in tri.items():
        um[(a, b)] = um.get((a, b), 0) + v / s
    return dict(sorted(um.items(), key=lambda kv: -kv[1]))


def allocate(P, N):
    """P: レースごとの確率リスト(降順)。点数の掛け算（組数）が N 以下で、3レースのカバー率の積が最大になる点数を選ぶ"""
    best, bk = -1, None
    for a in range(1, N + 1):
        for b in range(1, N // a + 1):
            c = N // (a * b)
            if c < 1:
                continue
            v = sum(P[0][:a]) * sum(P[1][:b]) * sum(P[2][:c])
            if v > best:
                best, bk = v, [a, b, c]
    return bk


def umatan_from_tan(h):
    """単勝オッズ → 馬単の確率（ハービル式：2着は残りの単勝確率の比）"""
    tan = {int(a): float(b) for a, b, _, _ in tanfuku(h) if b.replace('.', '').isdigit() and float(b) > 0}
    S = sum(1 / v for v in tan.values()); p = {k: (1 / v) / S for k, v in tan.items()}
    um = {}
    for a in p:
        for b in p:
            if a != b:
                um[(a, b)] = p[a] * p[b] / (1 - p[a])
    return um


def blend(u3, ut, w):
    """3連単換算 u3 と 単勝換算 ut を w:(1-w) で混ぜる（w=1 なら3連単だけ）"""
    keys = set(u3) | set(ut)
    um = {k: w * u3.get(k, 0) + (1 - w) * ut.get(k, 0) for k in keys}
    return dict(sorted(um.items(), key=lambda kv: -kv[1]))


def harville(p):
    um = {}
    for a in p:
        for b in p:
            if a != b:
                um[(a, b)] = p[a] * p[b] / (1 - p[a])
    return um


def umatan_from_model(deba_html, nh, place='船橋'):
    """自前モデル（nar_model）の勝率 → 馬単"""
    import subprocess, re
    out = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nar_model.py'), 'predict', deba_html, str(nh), place],
                         capture_output=True, text=True).stdout
    p = {int(m.group(1)): float(m.group(2)) / 100 for m in re.finditer(r'^(\d+)番 ([\d.]+)%', out, re.M)}
    return harville(p)


if __name__ == '__main__':
    # 使い方: python tools/triple.py N 3連単.html×3 単勝.html×3 出馬表.html×3 頭数,頭数,頭数
    #   10R は3連単のみ、11R・12R は 3連単・単勝・自前モデルを 1/3 ずつ
    N = int(sys.argv[1]); files = sys.argv[2:5]
    UM = [umatan_probs(open(f, encoding='utf-8', errors='replace').read()) for f in files]
    if len(sys.argv) >= 12:
        UT = [umatan_from_tan(open(f, encoding='utf-8', errors='replace').read()) for f in sys.argv[5:8]]
        NH = [int(v) for v in sys.argv[11].split(',')]
        UMd = [umatan_from_model(sys.argv[8 + i], NH[i]) for i in range(3)]
        W = [(1, 0, 0), (1 / 3, 1 / 3, 1 / 3), (1 / 3, 1 / 3, 1 / 3)]
        UM = [dict(sorted({k: W[i][0] * UM[i].get(k, 0) + W[i][1] * UT[i].get(k, 0) + W[i][2] * UMd[i].get(k, 0)
                           for k in set(UM[i]) | set(UT[i]) | set(UMd[i])}.items(), key=lambda kv: -kv[1])) for i in range(3)]
    P = [list(u.values()) for u in UM]
    k = allocate(P, N)
    tot = 1
    for i, u in enumerate(UM):
        items = list(u.items())[:k[i]]
        c = sum(v for _, v in items); tot *= c
        print(f"[{i+1}レース目] {k[i]}点 カバー率{c*100:.0f}%")
        for (a, b), v in items:
            print(f"  {a}→{b}  {v*100:.1f}%")
    n = k[0] * k[1] * k[2]
    print(f"3レース合計の的中見込み {tot*100:.1f}%（{k[0]}×{k[1]}×{k[2]}＝{n}組 {n*50}円）")
