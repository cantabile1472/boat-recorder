# Bluesky 投稿用の画像（1200x675）を作る
#  pick_card : 買い目の投稿
#  hit_card  : 的中の投稿（分刻みの3連複オッズの動き＝公開データベースと同じ時点だけ）
#  summary_card : 毎晩の結果（日ごとの回収率と、投稿開始からの累計）
#  40秒前・15秒前のオッズ、判断基準、EVは画像にも載せないこと
import os, glob
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

for p in glob.glob('/usr/share/fonts/**/NotoSansCJK*.tt*', recursive=True) + glob.glob(os.path.join(os.path.dirname(__file__), '..', 'fonts', '*')):
    try:
        font_manager.fontManager.addfont(p)
    except Exception:
        pass
plt.rcParams['font.family'] = ['Noto Sans CJK JP', 'Noto Sans JP', 'IPAexGothic', 'sans-serif']

BG, INK, SUB, ACC, HIT, GRID = '#0f1b2d', '#f4f1ea', '#9fb0c8', '#38bdf8', '#fbbf24', '#24344d'
BOAT = {1: ('#ffffff', '#111'), 2: ('#1f1f1f', '#fff'), 3: ('#e53935', '#fff'), 4: ('#1e63d6', '#fff'), 5: ('#f2c200', '#111'), 6: ('#2e9e4f', '#fff')}
W, H = 12, 6.75


def _fig():
    f = plt.figure(figsize=(W, H), dpi=100); f.patch.set_facecolor(BG)
    return f


def _boats(f, x, y, combo, size=0.085):
    """艇番を公式の色の丸で描く（combo='3-4-5'）"""
    for i, b in enumerate(int(c) for c in combo.split('-')):
        bg, fg = BOAT[b]
        ax = f.add_axes([x + i * (size * 0.62), y, size * 0.56, size]); ax.axis('off')
        ax.add_patch(plt.Rectangle((0, 0), 1, 1, color=bg, ec='#555', lw=1.5, transform=ax.transAxes))
        ax.text(0.5, 0.47, str(b), ha='center', va='center', fontsize=40, fontweight='bold', color=fg, transform=ax.transAxes)


def _foot(f, txt='@kuzuboat.bsky.social'):
    f.text(0.97, 0.04, txt, ha='right', va='bottom', color=SUB, fontsize=13)


def pick_card(place, R, deadline, combos, out):
    f = _fig()
    f.text(0.05, 0.86, f'{place}  {R}R', color=INK, fontsize=46, fontweight='bold', va='center')
    f.text(0.05, 0.75, '3連複', color=SUB, fontsize=22, va='center')
    for k, c in enumerate(combos[:3]):
        _boats(f, 0.06, 0.48 - k * 0.19, c, size=0.15)
    f.text(0.55, 0.62, '締切', color=SUB, fontsize=22); f.text(0.55, 0.47, deadline, color=INK, fontsize=64, fontweight='bold')
    f.text(0.55, 0.36, f'{len(combos[:3])}点・各100円', color=SUB, fontsize=20)
    f.text(0.55, 0.22, '結果は当たり外れ全部投稿します', color=SUB, fontsize=16)
    _foot(f); f.savefig(out, facecolor=BG); plt.close(f)


def hit_card(place, R, combo, pay, series, out):
    """series: [(ラベル, オッズ), ...]（60分前〜1分前）"""
    f = _fig()
    f.text(0.05, 0.88, '的中', color=HIT, fontsize=30, fontweight='bold', va='center')
    f.text(0.16, 0.88, f'{place}  {R}R　3連複', color=INK, fontsize=30, fontweight='bold', va='center')
    _boats(f, 0.06, 0.58, combo, size=0.17)
    f.text(0.06, 0.40, '100円 →', color=SUB, fontsize=24, va='center')
    f.text(0.06, 0.27, f'{pay:,}円', color=HIT, fontsize=64, fontweight='bold', va='center')
    s = [(l, o) for l, o in series if o and o > 0]
    if len(s) >= 2:
        ax = f.add_axes([0.52, 0.18, 0.43, 0.58]); ax.set_facecolor(BG)
        xs = range(len(s)); ys = [o for _, o in s]
        ax.plot(xs, ys, color=ACC, lw=3, marker='o', ms=7)
        ax.set_xticks(list(xs)); ax.set_xticklabels([l.replace('分前', '') for l, _ in s], color=SUB, fontsize=12)
        ax.tick_params(colors=SUB, labelsize=12); [sp.set_visible(False) for sp in ax.spines.values()]
        ax.grid(axis='y', color=GRID, lw=1); ax.set_axisbelow(True)
        ax.set_title('この組のオッズの動き', color=SUB, fontsize=14, loc='left')
        ax.set_xlabel('締切までの分数', color=SUB, fontsize=12)
        ax.text(len(s) - 1, ys[-1], f' {ys[-1]:.1f}倍', color=INK, fontsize=14, va='center')
        ax.set_ylim(min(ys) * 0.85, max(ys) * 1.15)
    _foot(f); f.savefig(out, facecolor=BG); plt.close(f)


def summary_card(day_label, days, today, total, out):
    """days: [(日付'11/13', 点数, 払戻合計円), ...]  today/total: (点数, 的中, 回収率%)"""
    f = _fig()
    f.text(0.05, 0.89, f'{day_label} の結果', color=INK, fontsize=34, fontweight='bold', va='center')
    f.text(0.05, 0.74, '本日', color=SUB, fontsize=18); f.text(0.05, 0.62, f'{today[2]}%', color=HIT if today[2] >= 100 else INK, fontsize=54, fontweight='bold')
    f.text(0.05, 0.55, f'{today[0]}点・的中{today[1]}本', color=SUB, fontsize=16)
    f.text(0.05, 0.40, '投稿開始から', color=SUB, fontsize=18); f.text(0.05, 0.28, f'{total[2]}%', color=HIT if total[2] >= 100 else INK, fontsize=54, fontweight='bold')
    f.text(0.05, 0.21, f'{total[0]}点・的中{total[1]}本', color=SUB, fontsize=16)
    ax = f.add_axes([0.42, 0.16, 0.53, 0.62]); ax.set_facecolor(BG)
    lab = [d for d, _, _ in days]; roi = [p / max(n, 1) for _, n, p in days]
    cum, cn, cp = [], 0, 0
    for _, n, p in days:
        cn += n; cp += p; cum.append(cp / max(cn, 1))
    ax.bar(range(len(days)), roi, color=[HIT if r >= 100 else '#3b5170' for r in roi], width=0.6, label='日ごと')
    ax.plot(range(len(days)), cum, color=ACC, lw=3, marker='o', ms=7, label='累計')
    ax.axhline(100, color=SUB, lw=1, ls='--')
    ax.set_xticks(range(len(days))); ax.set_xticklabels(lab, color=SUB, fontsize=12)
    ax.tick_params(colors=SUB, labelsize=12); [sp.set_visible(False) for sp in ax.spines.values()]
    ax.set_ylabel('回収率 %', color=SUB, fontsize=12); ax.grid(axis='y', color=GRID); ax.set_axisbelow(True)
    leg = ax.legend(loc='lower center', bbox_to_anchor=(0.5, 1.0), ncol=2, frameon=False, fontsize=12); [t.set_color(SUB) for t in leg.get_texts()]
    _foot(f); f.savefig(out, facecolor=BG); plt.close(f)


if __name__ == '__main__':
    import sys
    o = sys.argv[1] if len(sys.argv) > 1 else '.'
    pick_card('徳山', 1, '08:39', ['2-4-5', '1-5-6'], os.path.join(o, 'pick.png'))
    hit_card('江戸川', 2, '3-4-5', 1490, [('60分前', 12.2), ('30分前', 16.5), ('15分前', 11.5), ('10分前', 16.0), ('5分前', 16.1), ('3分前', 14.4), ('2分前', 14.4), ('1分前', 15.0)], os.path.join(o, 'hit.png'))
    summary_card('11/15', [('11/13', 88, 6424), ('11/14', 104, 6864), ('11/15', 78, 8502)], (78, 6, 109), (280, 16, 78), os.path.join(o, 'summary.png'))
