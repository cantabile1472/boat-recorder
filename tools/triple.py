# トリプル馬単の買い目：3レースの3連単オッズ（Odds3LenTan のHTML）から馬単の確率を出し、
# 3レースの的中確率の積が最大になるように N 組を配分する
#  使い方: python tools/triple.py N 10R.html 11R.html 12R.html
import sys, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nar_recorder import rank_table


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


if __name__ == '__main__':
    N = int(sys.argv[1]); files = sys.argv[2:]
    UM = [umatan_probs(open(f, encoding='utf-8', errors='replace').read()) for f in files]
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
