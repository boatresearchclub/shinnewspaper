"""
tenji_all_venues_v2.py  —  全会場テン展示取得（競合修正版）
=============================================================
【修正点】
  - 締め切り時刻の取得を「起動時に順番に実施」してから並列スタート
    → Playwright の同時起動による競合エラーを解消

【使い方】
  # 今日の全開催会場を自動検出して取得
  python tenji_all_venues_v2.py

  # 日付を指定
  python tenji_all_venues_v2.py --date 2026-04-25

  # 会場を絞る
  python tenji_all_venues_v2.py --venue heiwajima tokoname gamagori

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
from tenji_scheduler_v2 import run_scheduler

# ─────────────────────────────────────────────────────────────
# 定数
# ─────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────
# 当日の開催会場を取得
# ─────────────────────────────────────────────────────────────
def fetch_active_venues(date_str: str) -> list:
    import re, time as t
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    from bs4 import BeautifulSoup

    hd = date_str.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={hd}"
    print(f"[会場一覧] {date_str} の開催会場を取得中...")

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
        except Exception:
            html = page.content()
        finally:
            browser.close()

    soup = BeautifulSoup(html, "html.parser")
    venues = []
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
    return venues


# ─────────────────────────────────────────────────────────────
# Step1: 締め切り時刻を順番に取得（並列しない）
# ─────────────────────────────────────────────────────────────
def collect_all_deadlines(venues: list, date_str: str) -> dict:
    """
    venues リストを順番に処理し、各会場の締め切り時刻を取得。
    Playwright を1会場ずつ起動することで競合を回避。

    returns: {slug: {1: "HH:MM", 2: "HH:MM", ...}, ...}
    """
    all_deadlines = {}
    total = len(venues)

    for i, v in enumerate(venues, 1):
        slug = v["slug"]
        name = v["name"]
        print(f"  [{i}/{total}] {name} 締め切り時刻取得中...", end=" ", flush=True)
        try:
            dl = fetch_deadlines_official(slug, date_str)
            if dl:
                all_deadlines[slug] = dl
                print(f"→ {len(dl)}R分取得")
            else:
                print("→ データなし（非開催の可能性）")
        except Exception as e:
            print(f"→ エラー: {e}")
        time.sleep(1)  # 連続アクセスに1秒インターバル

    return all_deadlines


# ─────────────────────────────────────────────────────────────
# Step2: 各会場を並列実行（締め切り時刻は取得済み）
# ─────────────────────────────────────────────────────────────
def venue_worker(venue_info: dict, date_str: str,
                 deadlines: dict,
                 window_minutes: int, poll_interval: int,
                 out_dir: Path,
                 results: dict, lock: threading.Lock):
    slug = venue_info["slug"]
    name = venue_info["name"]

    try:
        run_scheduler(
            venue_slug=slug,
            date_str=date_str,
            deadlines=deadlines,
            window_minutes=window_minutes,
            poll_interval=poll_interval,
            out_dir=out_dir,
            races=None,
        )
        results[name] = "✓ 完了"
    except Exception as e:
        with lock:
            print(f"\n[{name}] エラー: {e}")
        results[name] = f"✗ エラー: {e}"


# ─────────────────────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="全会場テン展示自動取得（競合修正版）",
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
    print(f"  テン展示 全会場取得")
    print(f"  日付: {date_str}")
    print(f"  ウィンドウ: 締め切り{args.window_minutes}分前〜締め切り時刻")
    print(f"  ポーリング: {args.poll_interval}秒ごと")
    print("=" * 65)

    # ── 会場リスト決定 ──
    if args.venue:
        venues = []
        for v in args.venue:
            slug = VENUE_SLUG.get(v, v)
            name = next((n for n, s in VENUE_SLUG.items() if s == slug), slug)
            jcd  = next((k for k, s in SLUG_LIST.items() if s == slug), "??")
            venues.append({"jcd": jcd, "slug": slug, "name": name})
    else:
        venues = fetch_active_venues(date_str)

    if not venues:
        print("\n[ERROR] 開催会場が見つかりませんでした")
        print("  → --venue heiwajima tokoname ... で手動指定してください")
        return

    print(f"\n対象会場: {len(venues)}場")
    for v in venues:
        print(f"  {v['name']} ({v['slug']})")

    # ── Step1: 締め切り時刻を順番に取得 ──
    print(f"\n【Step1】締め切り時刻を取得中（順番に処理）")
    all_deadlines = collect_all_deadlines(venues, date_str)

    if not all_deadlines:
        print("\n[ERROR] 締め切り時刻が1件も取得できませんでした")
        print("  → debug_deadlines.py で HTML 構造を確認してください")
        print("    python debug_deadlines.py --venue heiwajima --date", date_str)
        return

    # 取得結果を表示
    print(f"\n取得結果:")
    active_venues = []
    for v in venues:
        slug = v["slug"]
        dl = all_deadlines.get(slug, {})
        if dl:
            first = min(dl.keys())
            last  = max(dl.keys())
            print(f"  {v['name']}: {len(dl)}R ({dl[first]}〜{dl[last]})")
            active_venues.append(v)
        else:
            print(f"  {v['name']}: 取得なし（スキップ）")

    if not active_venues:
        print("\n有効な会場がありません。終了します。")
        return

    # ── Step2: 各会場を並列実行 ──
    print(f"\n【Step2】{len(active_venues)}会場を並列実行開始")

    results = {}
    lock = threading.Lock()
    threads = []

    for v in active_venues:
        slug = v["slug"]
        t = threading.Thread(
            target=venue_worker,
            args=(v, date_str, all_deadlines[slug],
                  args.window_minutes, args.poll_interval,
                  out_dir, results, lock),
            name=v["name"],
            daemon=True,
        )
        threads.append(t)

    for t in threads:
        t.start()
        time.sleep(0.3)

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n\n[終了] 中断されました")
        return

    # ── サマリー ──
    print(f"\n{'='*65}")
    print("  全会場 完了サマリー")
    print("=" * 65)
    for name, status in results.items():
        print(f"  {name}: {status}")
    print(f"\n  保存先: {out_dir or '（保存なし）'}")


if __name__ == "__main__":
    main()
