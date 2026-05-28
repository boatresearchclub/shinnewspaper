"""
tenji_scheduler_v2.py  —  締め切り時刻ベースのテン展示自動取得スケジューラ
=============================================================================
【動作フロー】
  1. 当日の全レース締め切り時刻を取得（boatrace.jp 公式 or 手動入力）
  2. 各レースの「締め切りN分前」から「締め切り時刻」まで定期ポーリング
  3. テン展示データを取得できたら保存、次のレースへ

【使い方】
  python tenji_scheduler_v2.py --venue heiwajima --date 2026-04-25
  python tenji_scheduler_v2.py --venue heiwajima --date 2026-04-25 \
    --deadlines "1=10:15,2=10:45,3=11:15,..."
  python tenji_scheduler_v2.py --venue heiwajima --date 2026-04-25 \
    --window-minutes 15 --poll-interval 60

【v2からの変更点】
  - BrowserSession を run_scheduler 全体で1回だけ起動し、全レース使い回す
    → Playwright 起動コスト（3〜5秒/回）を完全に排除
  - 適応型ポーリング間隔を導入
      締め切り5分以上前 : poll_interval（デフォルト60秒）
      締め切り1〜5分前  : 15秒
      締め切り1分前以内 : 10秒（サーバー負荷を考慮）
    → データ公開直後に素早く検知できる
  - poll_race() に session 引数を追加（BrowserSession 使い回し）

依存:
  pip install playwright beautifulsoup4 pandas
  playwright install chromium
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, date as date_cls
from pathlib import Path

from fetch_tenji import (
    VENUE_SLUG, build_url, fetch_html, parse_tenji,
    save_csv, save_json, _fmt, BrowserSession, fetch_one,
)
from fetch_deadlines import (
    VENUE_JCD, fetch_deadlines_official, fetch_deadlines_from_boaters
)


# ─────────────────────────────────────────────────────────────
# 時刻ユーティリティ
# ─────────────────────────────────────────────────────────────
def parse_hhmm(s: str, base_date: date_cls = None) -> datetime:
    """
    'HH:MM' → 指定日付の datetime（base_date 省略時は今日）

    【修正】旧実装は datetime.now().replace(...) を使っていたため、
    呼び出すたびに秒・マイクロ秒が変化し seconds_until() の計算がズレるバグがあった。
    datetime() で直接組み立てることで常に HH:MM:00.000000 固定になる。
    """
    h, m = map(int, s.strip().split(":"))
    d = base_date or date_cls.today()
    return datetime(d.year, d.month, d.day, h, m, 0, 0)


def seconds_until(target: datetime) -> float:
    return (target - datetime.now()).total_seconds()


def adaptive_sleep(remain_sec: float, poll_interval: int) -> float:
    """
    締め切りまでの残り時間に応じてポーリング間隔を動的に短縮する。

    残り5分超  → poll_interval（通常間隔、デフォルト60秒）
    残り1〜5分 → 15秒
    残り1分以内 → 10秒（サーバー負荷を考慮）

    戻り値: 実際に sleep する秒数
    """
    if remain_sec > 300:
        return min(poll_interval, remain_sec - 5)
    elif remain_sec > 60:
        return 15
    else:
        return 10


# ─────────────────────────────────────────────────────────────
# 1レース分のポーリング処理
# ─────────────────────────────────────────────────────────────
def poll_race(venue_slug: str, date_str: str, race: int,
              deadline: datetime, window_minutes: int,
              poll_interval: int, out_dir: Path,
              session: BrowserSession = None) -> bool:
    """
    締め切り window_minutes 分前から deadline まで適応型ポーリングで取得を試みる。
    成功したら True を返す。

    session: BrowserSession インスタンス（渡すとブラウザを使い回す）
    """
    start_time = deadline - timedelta(minutes=window_minutes)
    now = datetime.now()

    if now < start_time:
        wait_sec = (start_time - now).total_seconds()
        print(f"  [{race}R] 取得ウィンドウ開始まで {wait_sec:.0f}秒待機 "
              f"({start_time.strftime('%H:%M')}〜{deadline.strftime('%H:%M')})")
        time.sleep(wait_sec)

    attempt = 0
    while datetime.now() <= deadline:
        attempt += 1
        now_str = datetime.now().strftime("%H:%M:%S")
        remain  = seconds_until(deadline)
        print(f"\n  [{race}R] {now_str}  取得試行 #{attempt} "
              f"(締切 {deadline.strftime('%H:%M')} まで {remain:.0f}秒)")

        url = build_url(venue_slug, date_str, race)
        try:
            html = fetch_html(url, session=session)
            rows = parse_tenji(html, venue_slug, date_str, race)
        except Exception as e:
            print(f"    [ERROR] {e}")
            rows = []

        if rows:
            print(f"    ✓ 展示データ確認 ({len(rows)}艇) → モーター・風情報も含めて本取得します")
            # ★ fetch_one に委譲してモーター・風情報も取得・保存する
            try:
                fetch_one(venue_slug, date_str, race, out_dir, session=session)
            except Exception as e:
                print(f"    [WARN] fetch_one エラー: {e}  →展示データのみ保存")
                if out_dir:
                    save_csv(rows, out_dir, venue_slug, date_str, race)
                    save_json(rows, out_dir, venue_slug, date_str, race)
            return True

        # ★ 適応型ポーリング間隔
        remain = seconds_until(deadline)
        if remain <= 0:
            print(f"    締め切り時刻を過ぎました ({race}R 取得失敗)")
            break

        sleep_sec = adaptive_sleep(remain, poll_interval)
        print(f"    データ未公開。{sleep_sec:.0f}秒後に再試行 "
              f"[残り{remain:.0f}秒 / 間隔{sleep_sec:.0f}秒]")
        time.sleep(sleep_sec)

    return False


# ─────────────────────────────────────────────────────────────
# メインスケジューラ
# ─────────────────────────────────────────────────────────────
def run_scheduler(venue_slug: str, date_str: str,
                  deadlines: dict,
                  window_minutes: int = 15,
                  poll_interval: int = 60,
                  out_dir: Path = None,
                  races: list = None):
    """
    deadlines に従って各レースのテン展示を自動取得する。
    ブラウザは全レース共通で1回だけ起動し使い回す。
    """
    if not deadlines:
        print("[ERROR] 締め切り時刻が取得できませんでした")
        return

    race_nums = sorted(deadlines.keys())
    if races:
        race_nums = [r for r in race_nums if r in races]

    print(f"\n{'='*65}")
    print(f"  テン展示 自動取得スケジューラ")
    print(f"  場: {venue_slug}  日付: {date_str}")
    print(f"  取得ウィンドウ: 締め切り {window_minutes}分前 〜 締め切り時刻")
    print(f"  ポーリング間隔: 適応型（通常{poll_interval}秒 / 直前5分15秒 / 直前1分10秒）")
    print(f"{'='*65}")
    base_date_display = datetime.strptime(date_str, "%Y-%m-%d").date()
    print(f"\n  レース別スケジュール:")
    for r in race_nums:
        dl_str = deadlines[r]
        dl_dt = parse_hhmm(dl_str, base_date_display)
        start_dt = dl_dt - timedelta(minutes=window_minutes)
        print(f"    {r:>2}R  締切={dl_str}  取得開始={start_dt.strftime('%H:%M')}")

    results = {}
    base_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    # ★ ブラウザを1回だけ起動して全レース使い回す
    print(f"\n  ブラウザを起動します...")
    with BrowserSession() as session:
        print(f"  ブラウザ起動完了。スケジューラ開始。\n")

        for race in race_nums:
            dl_str = deadlines[race]
            # ★ date_str を渡すことで日付跨ぎや未来日付の計算ズレを防止
            deadline = parse_hhmm(dl_str, base_date)

            # ★ now をループ毎に取得（前レース処理後に古い値を使うバグを修正）
            if deadline < datetime.now() - timedelta(minutes=1):
                print(f"\n  [{race}R] 締め切り済み ({dl_str}) — スキップ")
                continue

            start_time = deadline - timedelta(minutes=window_minutes)
            wait_sec = (start_time - datetime.now()).total_seconds()
            if wait_sec > 0:
                print(f"\n  [{race}R] {wait_sec/60:.1f}分後に取得開始 "
                      f"({start_time.strftime('%H:%M')} — 締切 {dl_str})")
                while (s := seconds_until(start_time)) > 30:
                    print(f"    待機中... 開始まで {s/60:.1f}分", end="\r")
                    time.sleep(30)
                remaining = seconds_until(start_time)
                if remaining > 0:
                    time.sleep(remaining)

            ok = poll_race(
                venue_slug, date_str, race, deadline,
                window_minutes, poll_interval, out_dir,
                session=session,   # ★ セッションを渡す
            )
            results[race] = "✓ 成功" if ok else "✗ 失敗"

    # サマリー
    print(f"\n{'='*65}")
    print("  取得結果サマリー")
    print(f"{'='*65}")
    for r, status in results.items():
        print(f"    {r:>2}R  {status}  (締切: {deadlines[r]})")
    ok_count = sum(1 for s in results.values() if "成功" in s)
    print(f"\n  合計: {ok_count}/{len(results)} レース取得成功")


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────
def parse_manual_deadlines(s: str) -> dict:
    result = {}
    for part in s.split(","):
        part = part.strip()
        if "=" in part:
            rno, t = part.split("=", 1)
            result[int(rno.strip())] = t.strip()
    return result


def main():
    ap = argparse.ArgumentParser(
        description="締め切り時刻ベースのテン展示自動取得スケジューラ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--venue", required=True,
        help="場スラッグ(heiwajima等) または日本語名(平和島等)")
    ap.add_argument("--date", default=None,
        help="日付 YYYY-MM-DD（デフォルト: 今日）")
    ap.add_argument("--deadlines", default=None,
        help="手動で締め切り時刻を指定: '1=10:15,2=10:45,...'")
    ap.add_argument("--source", default="official",
        choices=["official", "boaters"],
        help="締め切り時刻の取得元 (official=boatrace.jp, boaters=boaters-boatrace.com)")
    ap.add_argument("--window-minutes", type=int, default=15,
        help="締め切り何分前から取得開始するか（デフォルト: 15）")
    ap.add_argument("--poll-interval", type=int, default=60,
        help="通常ポーリング間隔(秒)（デフォルト: 60。直前5分は15秒、1分以内は10秒に自動短縮）")
    ap.add_argument("--races", default=None,
        help="対象レース番号 カンマ区切り（例: 1,3,5）。省略時は全レース")
    ap.add_argument("--out", default="./tenji_data", help="保存先ディレクトリ")
    ap.add_argument("--no-save", action="store_true", help="保存しない")
    args = ap.parse_args()

    venue = VENUE_SLUG.get(args.venue, args.venue)
    date_str = args.date or date_cls.today().strftime("%Y-%m-%d")
    out_dir = None if args.no_save else Path(args.out)
    races = [int(r) for r in args.races.split(",")] if args.races else None

    if args.deadlines:
        deadlines = parse_manual_deadlines(args.deadlines)
        print(f"[手動入力] {len(deadlines)}R分の締め切り時刻を設定しました")
    elif args.source == "boaters":
        print(f"[boaters] 締め切り時刻を取得中...")
        deadlines = fetch_deadlines_from_boaters(venue, date_str)
    else:
        print(f"[公式] boatrace.jp から締め切り時刻を取得中...")
        try:
            deadlines = fetch_deadlines_official(venue, date_str)
        except Exception as e:
            print(f"  [ERROR] 公式から取得失敗: {e}")
            print("  → --deadlines オプションで手動入力してください")
            sys.exit(1)

    if not deadlines:
        print("[ERROR] 締め切り時刻を取得できませんでした")
        print("  → --deadlines '1=10:15,2=10:45,...' で手動入力してください")
        sys.exit(1)

    print(f"  取得済み締め切り時刻: {len(deadlines)}R分")
    for r in sorted(deadlines):
        print(f"    {r:>2}R → {deadlines[r]}")

    try:
        run_scheduler(
            venue_slug=venue,
            date_str=date_str,
            deadlines=deadlines,
            window_minutes=args.window_minutes,
            poll_interval=args.poll_interval,
            out_dir=out_dir,
            races=races,
        )
    except KeyboardInterrupt:
        print("\n\n[終了] ユーザーによる中断")


if __name__ == "__main__":
    main()
