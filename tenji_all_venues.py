"""
tenji_all_venues.py  —  全会場（または指定複数会場）並列テン展示取得
======================================================================
【使い方】

  # 今日の全開催会場を自動検出して取得
  python tenji_all_venues.py

  # 日付を指定
  python tenji_all_venues.py --date 2026-04-25

  # 会場を絞る
  python tenji_all_venues.py --venue heiwajima tokoname gamagori

  # 締め切り15分前から30秒ごとにポーリング
  python tenji_all_venues.py --window-minutes 15 --poll-interval 30

【動作】
  - 当日の開催会場を boatrace.jp から自動取得
  - 各会場を別スレッドで並列実行（会場同士は干渉しない）
  - 締め切り15分前〜締め切り時刻の間だけ取得を試みる
  - データは ./tenji_data/ に保存

依存:
  pip install playwright beautifulsoup4 pandas
  playwright install chromium
"""

import argparse
import time
import threading
from datetime import datetime, date as date_cls
from pathlib import Path

from fetch_tenji import VENUE_SLUG, _fmt
from fetch_deadlines import VENUE_JCD, fetch_deadlines_official
from tenji_scheduler_v2 import run_scheduler, parse_manual_deadlines


# ─────────────────────────────────────────────────────────────
# 当日の開催会場を boatrace.jp から取得
# ─────────────────────────────────────────────────────────────
# jcd → venue_slug の逆引き
JCD_TO_SLUG = {v: k for k, v in VENUE_JCD.items() if len(k) == 2}  # 数字コードのみ
JCD_TO_NAME = {
    "01":"桐生","02":"戸田","03":"江戸川","04":"平和島","05":"多摩川",
    "06":"浜名湖","07":"蒲郡","08":"常滑","09":"津","10":"三国",
    "11":"びわこ","12":"住之江","13":"尼崎","14":"鳴門","15":"丸亀",
    "16":"児島","17":"宮島","18":"徳山","19":"下関","20":"若松",
    "21":"芦屋","22":"福岡","23":"唐津","24":"大村",
}
SLUG_LIST = {
    "01":"kiryu","02":"toda","03":"edogawa","04":"heiwajima","05":"tamagawa",
    "06":"hamanako","07":"gamagori","08":"tokoname","09":"tsu","10":"mikuni",
    "11":"biwako","12":"suminoe","13":"amagasaki","14":"naruto","15":"marugame",
    "16":"kojima","17":"miyajima","18":"tokuyama","19":"shimonoseki","20":"wakamatsu",
    "21":"ashiya","22":"fukuoka","23":"karatsu","24":"omura",
}


def fetch_active_venues(date_str: str) -> list:
    """
    boatrace.jp のトップ or 開催一覧から、当日の開催会場リストを取得。
    returns: [{"jcd": "04", "slug": "heiwajima", "name": "平和島"}, ...]
    """
    import re, time as t
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    from bs4 import BeautifulSoup

    hd = date_str.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={hd}"

    print(f"[会場一覧] boatrace.jp から当日開催会場を取得中... ({date_str})")
    html = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        try:
            page.goto(url, wait_until="networkidle", timeout=20000)
            t.sleep(2)
            html = page.content()
        except PWTimeout:
            html = page.content()
        finally:
            browser.close()

    soup = BeautifulSoup(html, "html.parser")
    venues = []

    # jcd=XX のパターンをリンクから探す
    seen = set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"jcd=(\d{2})", a["href"])
        if m:
            jcd = m.group(1)
            if jcd not in seen and jcd in SLUG_LIST:
                seen.add(jcd)
                venues.append({
                    "jcd":  jcd,
                    "slug": SLUG_LIST[jcd],
                    "name": JCD_TO_NAME.get(jcd, jcd),
                })

    if not venues:
        print("  [!] 会場一覧を自動取得できませんでした")
        print("      --venue で手動指定してください")

    return venues


# ─────────────────────────────────────────────────────────────
# 1会場分のスレッド処理
# ─────────────────────────────────────────────────────────────
def venue_thread(venue_info: dict, date_str: str,
                 window_minutes: int, poll_interval: int,
                 out_dir: Path, results: dict, lock: threading.Lock):
    slug = venue_info["slug"]
    name = venue_info["name"]
    jcd  = venue_info["jcd"]

    with lock:
        print(f"\n[{name}] 締め切り時刻を取得中...")

    try:
        deadlines = fetch_deadlines_official(slug, date_str)
    except Exception as e:
        with lock:
            print(f"[{name}] 締め切り時刻取得失敗: {e}")
        results[name] = {"error": str(e)}
        return

    if not deadlines:
        with lock:
            print(f"[{name}] 締め切り時刻なし（非開催の可能性）")
        results[name] = {"error": "締め切り時刻取得できず"}
        return

    with lock:
        print(f"[{name}] {len(deadlines)}R分の締め切り時刻取得完了")

    # スケジューラを実行（この関数はブロッキング）
    run_scheduler(
        venue_slug=slug,
        date_str=date_str,
        deadlines=deadlines,
        window_minutes=window_minutes,
        poll_interval=poll_interval,
        out_dir=out_dir,
        races=None,
    )

    results[name] = {"done": True}


# ─────────────────────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="全会場並列テン展示自動取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--venue", nargs="*", default=None,
        help="会場を絞る場合のみ指定（例: heiwajima tokoname）。省略で全開催会場")
    ap.add_argument("--date", default=None,
        help="日付 YYYY-MM-DD（省略で今日）")
    ap.add_argument("--window-minutes", type=int, default=15,
        help="締め切り何分前から取得開始するか（デフォルト: 15）")
    ap.add_argument("--poll-interval", type=int, default=60,
        help="ポーリング間隔(秒)（デフォルト: 60）")
    ap.add_argument("--out", default="./tenji_data",
        help="保存先ディレクトリ（デフォルト: ./tenji_data）")
    ap.add_argument("--no-save", action="store_true", help="保存しない")
    args = ap.parse_args()

    date_str = args.date or date_cls.today().strftime("%Y-%m-%d")
    out_dir  = None if args.no_save else Path(args.out)

    print("=" * 65)
    print(f"  テン展示 全会場並列取得")
    print(f"  日付: {date_str}")
    print(f"  取得ウィンドウ: 締め切り{args.window_minutes}分前〜締め切り時刻")
    print(f"  ポーリング間隔: {args.poll_interval}秒")
    print("=" * 65)

    # 会場リストを決定
    if args.venue:
        # 手動指定
        venues = []
        for v in args.venue:
            slug = VENUE_SLUG.get(v, v)
            # name を逆引き
            name = next((n for n, s in VENUE_SLUG.items() if s == slug), slug)
            jcd  = next((k for k, s in SLUG_LIST.items() if s == slug), "??")
            venues.append({"jcd": jcd, "slug": slug, "name": name})
    else:
        # 当日開催会場を自動取得
        venues = fetch_active_venues(date_str)

    if not venues:
        print("\n開催会場が見つかりませんでした。--venue で手動指定してください。")
        print("例: python tenji_all_venues.py --venue heiwajima tokoname")
        return

    print(f"\n対象会場 ({len(venues)}場):")
    for v in venues:
        print(f"  {v['name']} ({v['slug']})")

    # 各会場を別スレッドで並列実行
    threads = []
    results = {}
    lock = threading.Lock()

    for venue_info in venues:
        t = threading.Thread(
            target=venue_thread,
            args=(venue_info, date_str,
                  args.window_minutes, args.poll_interval,
                  out_dir, results, lock),
            name=venue_info["name"],
            daemon=True,
        )
        threads.append(t)

    print(f"\n{len(threads)}スレッドで並列実行開始...\n")
    for t in threads:
        t.start()
        time.sleep(0.5)  # 起動タイミングをずらす

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n\n[終了] ユーザーによる中断")
        return

    # 最終サマリー
    print(f"\n{'='*65}")
    print("  全会場 取得完了サマリー")
    print("=" * 65)
    for name, res in results.items():
        if "error" in res:
            print(f"  ✗ {name}: {res['error']}")
        else:
            print(f"  ✓ {name}: 完了")
    print(f"\n  保存先: {out_dir or '（保存なし）'}")


if __name__ == "__main__":
    main()
