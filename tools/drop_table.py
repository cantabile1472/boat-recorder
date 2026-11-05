# 戦略E用「下がり方の表」：1分前の下限オッズが締切で何割残るかを、券種×下限オッズ帯×期待値帯で集計する（競艇）
# 使い方:
#   python tools/drop_table.py build 20261104 [20261105 ...]   → data/drop_table.json と data/drop_table.md を作る
#   python tools/drop_table.py check 20261105                    → その日に表を当てはめて答え合わせ（data/日付/drop_check.md）
import sys, os, csv, json, statistics as st
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('NO_GIT', '1')
import strat_e as E

LO = [(1, 2), (2, 3), (3, 5), (5, 10), (10, 1e9)]
EV = [(0, 0.8), (0.8, 1.0), (1.0, 1.2), (1.2, 1.5), (1.5, 1e9)]
LAB_LO = ['2倍未満', '2〜3倍', '3〜5倍', '5〜10倍', '10倍以上']
LAB_EV = ['0.8未満', '0.8〜1.0', '1.0〜1.2', '1.2〜1.5', '1.5以上']


def band(v, bs):
    for i, (a, b) in enumerate(bs):
        if a <= v < b:
            return i
    return None


def samples(day, tmin=None, tmax=None):
    """競艇：1分前判定（スナップ3）の全候補と、締切の下限オッズ。tmin/tmax で締切時刻を絞れる（'HH:MM'）"""
    p = f'data/{day}/kyotei_odds_full.csv'
    if not os.path.exists(p):
        return []
    g = {}
    for r in csv.DictReader(open(p, encoding='utf-8')):
        x = g.setdefault((r['jcd'], r['R']), {})
        x.setdefault(r['snap'], {})[r['kind']] = r['values'].split()
        if r['snap'] == '3':
            x['t'] = r['time'][:5]
    P = dict(E.DEF); P['kinds'] = ['fuku', 'wide']
    out = []
    for (j, R_), s in g.items():
        if '3' not in s or 'close' not in s:
            continue
        if (tmin and s.get('t', '') < tmin) or (tmax and s.get('t', '') >= tmax):
            continue
        a, c = s['3'], s['close']
        if not all(k in a for k in ('tf', 'k', '3t')) or not all(k in c for k in ('tf', 'k')):
            continue
        pa = E.kyotei_parse(a['tf'], a['k'], a['3t'])
        pc = E.kyotei_parse(c['tf'], c['k'], c.get('3t', a['3t']))
        if not pa or not pc:
            continue
        for r in E.evaluate(*pa, P=P):
            kd, sel, lo, hi, p, ev = r[:6]
            cl = pc[0].get(int(sel)) if kd == '複勝' else pc[1].get(tuple(map(int, sel.split('-'))))
            if cl and lo > 0:
                out.append({'jcd': j, 'R': R_, 'kind': kd, 'sel': sel, 'lo': lo, 'p': p, 'ev': ev, 'lo_c': cl[0], 'hi_c': cl[1]})
    return out


def build(S):
    tb = {}
    for kd in ('複勝', 'ワイド'):
        for i in range(len(LO)):
            for k in range(len(EV)):
                L = [x['lo_c'] / x['lo'] for x in S if x['kind'] == kd and band(x['lo'], LO) == i and band(x['ev'], EV) == k]
                tb[f'{kd}|{i}|{k}'] = {'n': len(L), 'd': round(st.median(L), 3) if L else None}
    return tb


def coef(tb, kd, lo, ev, minn=5):
    i, k = band(lo, LO), band(ev, EV)
    c = tb.get(f'{kd}|{i}|{k}')
    if c and c['n'] >= minn and c['d']:
        return c['d']
    return None


def table_md(tb, title):
    L = [f'## {title}', '']
    for kd in ('複勝', 'ワイド'):
        L += [f'### {kd}（締切で下限オッズが何割残るか・カッコは件数）', '',
              '| 下限オッズ＼期待値 | ' + ' | '.join(LAB_EV) + ' |', '|---|' + '---|' * len(EV)]
        for i in range(len(LO)):
            cells = []
            for k in range(len(EV)):
                c = tb[f'{kd}|{i}|{k}']
                cells.append(f"{c['d']:.2f}（{c['n']}）" if c['d'] is not None else '－')
            L.append(f'| {LAB_LO[i]} | ' + ' | '.join(cells) + ' |')
        L.append('')
    return L


def check(tb, S, title):
    """表で予想した残り率と実際の残り率を比べる。予想締切期待値（期待値×係数）の帯ごとに、実際の締切期待値（確率×締切下限）も出す"""
    L = [f'## {title}', '', '| 券種 | 予想した締切期待値 | 件数 | 予想の残り率 | 実際の残り率 | 実際の締切期待値（確率×締切下限） |', '|---|---|---|---|---|---|']
    for kd in ('複勝', 'ワイド'):
        rows = []
        for x in S:
            if x['kind'] != kd:
                continue
            d = coef(tb, kd, x['lo'], x['ev'])
            if d:
                rows.append((x['ev'] * d, d, x['lo_c'] / x['lo'], x['p'] * x['lo_c']))
        for a, b in [(0, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0), (1.0, 9)]:
            g = [r for r in rows if a <= r[0] < b]
            if g:
                L.append(f'| {kd} | {a:.1f}〜{b if b < 9 else ""} | {len(g)} | {st.median([r[1] for r in g]):.2f} | {st.median([r[2] for r in g]):.2f} | {st.mean([r[3] for r in g]):.2f} |')
    return L


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'build':
        S = sum((samples(d) for d in sys.argv[2:]), [])
        tb = build(S)
        json.dump({'days': sys.argv[2:], 'table': tb}, open('data/drop_table.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
        open('data/drop_table.md', 'w', encoding='utf-8').write('\n'.join(table_md(tb, f"下がり方の表（{'・'.join(sys.argv[2:])}・{len(S)}件）")) + '\n')
        print('\n'.join(table_md(tb, '表')))
    elif cmd == 'split':      # 1日を前半で表を作って後半で確かめる
        d, t = sys.argv[2], sys.argv[3]
        tb = build(samples(d, tmax=t)); S2 = samples(d, tmin=t)
        print('\n'.join(table_md(tb, f'{d} {t}より前で作った表') + [''] + check(tb, S2, f'{t}以降で答え合わせ（{len(S2)}件）')))
    elif cmd == 'check':
        d = sys.argv[2]
        tb = json.load(open('data/drop_table.json', encoding='utf-8'))['table']
        S = samples(d)
        L = check(tb, S, f'{d}：表の当てはまり（{len(S)}件）')
        open(f'data/{d}/drop_check.md', 'w', encoding='utf-8').write('\n'.join(L) + '\n')
        print('\n'.join(L))
