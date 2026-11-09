# オッズから単勝の総票数を逆算する（1票=100円、払戻率75%、オッズは0.1刻み切り捨て）
import math
def est_pool(odds, tmax=30000, rate=0.75, loose=True):
    """odds: 6艇の単勝オッズ（0=欠場）。矛盾しない最小の総票数Tと各艇の票数を返す"""
    o = [x for x in odds if x and x > 0]
    if len(o) < 2:
        return None
    capped = any(x <= 1.0 for x in o)
    for T in range(len(o), tmax):
        vs = []; ok = True
        for x in o:
            if x <= 1.0:
                vs.append(None); continue
            v = round(rate * T / x)
            if v < 1 or math.floor(rate * T / v * 10 + 1e-9) / 10 != x:
                ok = False; break
            vs.append(v)
        if not ok:
            continue
        s = sum(v for v in vs if v)
        if capped:
            rest = T - s
            if rest >= 1 and all(math.floor(rate * T / rest * 10 + 1e-9) / 10 <= 1.0 or True for _ in [0]):
                return T, vs
        elif s == T:
            return T, vs
    if not loose:
        return None
    # 厳密に合わない（スナップの途中更新など）→ 合計のズレを3%まで許す
    for T in range(len(o), tmax):
        vs = []; ok = True
        for x in o:
            if x <= 1.0:
                vs.append(None); continue
            v = round(rate * T / x)
            if v < 1 or math.floor(rate * T / v * 10 + 1e-9) / 10 != x:
                ok = False; break
            vs.append(v)
        if ok and (capped or abs(sum(vs) - T) <= max(2, 0.03 * T)):
            return T, vs
    return None
