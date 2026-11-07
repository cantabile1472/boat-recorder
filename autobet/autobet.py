# 自動投票エージェント（日本のVPSで動かす）
#   ntfy の注文トピックを購読 → 注文が来たらテレボートに単勝を投票する
#   モード: dry（空撃ち：購入ボタンの手前で止めて画面を保存） / live（本番）
#   使い方: python3 autobet.py            （settings.json を読む）
#          python3 autobet.py test        （テスト注文を1件、空撃ちで流す）
import os, sys, json, time, datetime, re, threading, traceback, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent
LOG = HERE / 'logs'; LOG.mkdir(exist_ok=True)
SHOT = HERE / 'shots'; SHOT.mkdir(exist_ok=True)
S = json.load(open(HERE / 'settings.json', encoding='utf-8'))
STOP_FILE = HERE / 'STOP'            # このファイルがあると何も買わない（緊急停止）
RUN_FILE = HERE / 'RUN'              # このファイルが無いと何も買わない（安全弁：本番にするとき自分で作る）
JST = datetime.timezone(datetime.timedelta(hours=9))


def now():
    return datetime.datetime.now(JST)


def log(msg):
    line = f"{now():%m/%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with open(LOG / f"{now():%Y%m%d}.log", 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def notify(title, body):
    t = S.get('notify_topic')
    if not t:
        return
    try:
        rq = urllib.request.Request('https://ntfy.sh/' + t, data=(title + '\n' + body).encode('utf-8'), headers={'Priority': 'high'})
        urllib.request.urlopen(rq, timeout=10).read()
    except Exception as e:
        log('通知NG ' + repr(e))


# ---------------- 安全装置 ----------------
class Guard:
    def __init__(self):
        self.path = HERE / 'state.json'
        self.st = json.load(open(self.path)) if self.path.exists() else {}

    def today(self):
        d = f"{now():%Y%m%d}"
        if self.st.get('day') != d:
            self.st = {'day': d, 'spent': 0, 'done': []}
        return self.st

    def check(self, o, amount):
        st = self.today()
        key = f"{o['sport']}-{o['jcd']}-{o['R']}-{o['kind']}-{o['sel']}"
        if STOP_FILE.exists():
            return 'STOPファイルがあるので見送り'
        if key in st['done']:
            return '同じレースに投票済み'
        if st['spent'] + amount > S['max_per_day']:
            return f"1日の上限({S['max_per_day']}円)に達するので見送り"
        dl = datetime.datetime.strptime(o['deadline'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=JST)
        left = (dl - now()).total_seconds()
        if left < S.get('min_seconds_before_deadline', 15):
            return f"締切まで{left:.0f}秒しかないので見送り"
        if left > 1800:
            return '締切まで30分以上ある注文は不審なので見送り'
        return None

    def done(self, o, amount):
        st = self.today(); st['spent'] += amount
        st['done'].append(f"{o['sport']}-{o['jcd']}-{o['R']}-{o['kind']}-{o['sel']}")
        json.dump(st, open(self.path, 'w'))


def amount_for(o):
    a = S['amount_star'] if o.get('stars') else S['amount']
    return int(a // 100 * 100)


# ---------------- テレボート操作 ----------------
class Teleboat:
    """テレボート（ボートレースのインターネット投票）をブラウザで操作する。
    画面の部品（入力欄やボタン）は selectors.json にまとめてあり、実際の画面に合わせて調整する。"""

    def __init__(self, pw):
        self.sel = json.load(open(HERE / 'selectors.json', encoding='utf-8'))
        self.browser = pw.chromium.launch(headless=True, args=['--lang=ja-JP'])
        self.ctx = self.browser.new_context(locale='ja-JP', viewport={'width': 1280, 'height': 900},
                                            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36')
        self.page = self.ctx.new_page()
        self.logged_in_at = 0

    def shot(self, name):
        p = SHOT / f"{now():%Y%m%d_%H%M%S}_{name}"
        try:
            self.page.screenshot(path=str(p) + '.png', full_page=True)
            open(str(p) + '.html', 'w', encoding='utf-8').write(self.page.content())
        except Exception:
            pass

    def fill(self, key, value):
        self.page.fill(self.sel[key], str(value))

    def click(self, key):
        self.page.click(self.sel[key])

    def login(self):
        c = S['teleboat']
        self.page.goto(self.sel['login_url'], wait_until='domcontentloaded')
        self.shot('01_login')
        self.fill('member_no', c['member_no'])
        self.fill('pin', c['pin'])
        self.fill('auth_no', c['auth_no'])
        self.click('login_button')
        self.page.wait_for_load_state('domcontentloaded')
        time.sleep(1.5)
        self.shot('02_after_login')
        if self.sel.get('login_ok_text') and self.sel['login_ok_text'] not in self.page.content():
            raise RuntimeError('ログインできていない（login_ok_text が見つからない）')
        self.logged_in_at = time.time()
        log('ログインOK')

    def ensure_login(self):
        if time.time() - self.logged_in_at > S.get('relogin_minutes', 20) * 60:
            self.login()

    def bet_tansho(self, jcd, R, boat, amount, live):
        """単勝を1点買う。live=False なら購入ボタンの手前で止める"""
        self.ensure_login()
        url = self.sel['vote_url'].format(jcd=f"{int(jcd):02d}", R=int(R))
        self.page.goto(url, wait_until='domcontentloaded')
        time.sleep(1.0)
        self.shot('03_vote_page')
        if self.sel.get('select_tansho'):
            self.click('select_tansho'); time.sleep(0.5)
        self.click(self.sel['boat_button'].format(boat=int(boat)) if '{boat}' in self.sel['boat_button'] else 'boat_button')
        if self.sel.get('amount_input'):
            self.fill('amount_input', amount // 100 if self.sel.get('amount_in_units_of_100') else amount)
        if self.sel.get('add_button'):
            self.click('add_button'); time.sleep(0.5)
        self.shot('04_filled')
        if self.sel.get('confirm_button'):
            self.click('confirm_button'); time.sleep(1.0)
            self.shot('05_confirm')
        if self.sel.get('total_input'):
            self.fill('total_input', amount)
        if self.sel.get('pin_again_input'):
            self.fill('pin_again_input', S['teleboat']['pin'])
        if not live:
            self.shot('06_dry_stop')
            log(f"[空撃ち] {jcd} {R}R 単勝{boat} {amount}円 → 購入ボタンの手前で停止（shots を確認）")
            return 'dry'
        self.click('buy_button')
        self.page.wait_for_load_state('domcontentloaded'); time.sleep(1.5)
        self.shot('07_bought')
        html = self.page.content()
        ok = (self.sel.get('bought_ok_text') or '受付') in html
        log(f"[本番] {jcd} {R}R 単勝{boat} {amount}円 → {'購入OK' if ok else '確認できず（shots を見て）'}")
        return 'ok' if ok else 'unknown'


# ---------------- 注文の受信 ----------------
def subscribe(handler):
    """ntfy の注文トピックを購読し続ける（切れたら再接続）"""
    url = f"https://ntfy.sh/{S['order_topic']}/json"
    while True:
        try:
            rq = urllib.request.Request(url, headers={'Accept': 'application/json'})
            with urllib.request.urlopen(rq, timeout=None) as r:
                log('注文トピック購読中')
                for line in r:
                    try:
                        m = json.loads(line.decode('utf-8'))
                    except Exception:
                        continue
                    if m.get('event') != 'message':
                        continue
                    msg = m.get('message', '')
                    if msg.strip() == '停止':
                        STOP_FILE.touch(); log('「停止」を受信 → STOPファイル作成'); notify('自動投票 停止', 'STOPファイルを作ったので以後は買わない'); continue
                    if msg.strip() == '再開':
                        STOP_FILE.unlink(missing_ok=True); log('「再開」を受信'); continue
                    try:
                        o = json.loads(msg)
                    except Exception:
                        continue
                    threading.Thread(target=handler, args=(o,), daemon=True).start()
        except Exception as e:
            log('購読が切れた ' + repr(e) + ' → 5秒後に再接続')
            time.sleep(5)


def main():
    from playwright.sync_api import sync_playwright
    guard = Guard(); lock = threading.Lock()
    live = S.get('mode') == 'live' and RUN_FILE.exists()
    log(f"起動 モード={'本番' if live else '空撃ち'} 1点={S['amount']}円 ★={S['amount_star']}円 1日上限={S['max_per_day']}円")
    with sync_playwright() as pw:
        tb = Teleboat(pw)
        try:
            tb.login()
        except Exception:
            log('ログイン失敗\n' + traceback.format_exc()); tb.shot('login_fail')

        def handle(o):
            if o.get('sport') != 'kyotei' or o.get('kind') != '単勝':
                log(f"対象外の注文 {o}"); return
            amount = amount_for(o)
            why = guard.check(o, amount)
            if why:
                log(f"見送り {o['jcd']} {o['R']}R: {why}"); return
            with lock:
                try:
                    live_now = S.get('mode') == 'live' and RUN_FILE.exists() and not STOP_FILE.exists()
                    res = tb.bet_tansho(o['jcd'], o['R'], o['sel'], amount, live_now)
                    if res == 'ok':
                        guard.done(o, amount)
                        notify('自動投票 購入', f"競艇 {o['jcd']} {o['R']}R 単勝{o['sel']} {amount}円（{o.get('note','')}）")
                    elif res == 'unknown':
                        guard.done(o, amount)   # 二重買いを防ぐため、不明でも購入扱い
                        notify('自動投票 要確認', f"競艇 {o['jcd']} {o['R']}R 購入結果が確認できない。テレボートの投票履歴を見て")
                except Exception:
                    log('投票エラー\n' + traceback.format_exc()); tb.shot('error')
                    notify('自動投票 エラー', f"競艇 {o['jcd']} {o['R']}R で失敗。logs を見て")
                    try:
                        tb.login()
                    except Exception:
                        pass

        if len(sys.argv) > 1 and sys.argv[1] == 'test':
            dl = (now() + datetime.timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
            handle({'sport': 'kyotei', 'jcd': S.get('test_jcd', '04'), 'R': S.get('test_R', 1), 'kind': '単勝', 'sel': '1', 'deadline': dl, 'stars': 0, 'odds': 0, 'note': 'テスト'})
            return
        subscribe(handle)


if __name__ == '__main__':
    main()
