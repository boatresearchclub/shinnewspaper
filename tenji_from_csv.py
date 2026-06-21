"""
tenji_from_csv.py  —  既存CSVから締め切り時刻・会場を読んで自動取得
======================================================================
【使い方】

  # 毎日8時に自動起動するデイリーループモード（--date 省略時）
  python tenji_from_csv.py

  # フォルダを指定
  python tenji_from_csv.py --csv-dir "C:/Users/user/Desktop/データ収集/scripts/csv_output"

  # 日付を指定（その1日だけ実行して終了）
  python tenji_from_csv.py --date 2026-04-25

  # 締め切り25分前から30秒ごとにポーリング
  python tenji_from_csv.py --window-minutes 25 --poll-interval 30

【動作】
  1. csv_output フォルダ内の当日CSV（{会場}_{日付}.csv）を全部読む
  2. 各CSVから「会場スラッグ」と「レースごとの締切時刻」を取得
  3. 全会場を並列実行（Playwright の同時起動なし・競合なし）

  --date 省略時はデイリーループモード:
    - 毎朝8:00にCSVを読み込み → 全会場並列実行
    - 全レース完了後、翌日8:00まで待機 → 繰り返し
    - 8:00時点でCSVがまだ無ければ5分おきにリトライ（最大9:00まで）

依存:
  pip install playwright beautifulsoup4 pandas
  playwright install chromium
"""

import argparse
import re
import threading
import time
from datetime import datetime, timedelta, date as date_cls
from pathlib import Path

import pandas as pd

from fetch_tenji import VENUE_SLUG, build_url, fetch_html, parse_tenji, save_csv, save_json, _fmt
from tenji_scheduler_v2 import run_scheduler

# ─────────────────────────────────────────────────────────────
# 会場名 → URLスラッグ（CSVの「会場」列と対応）
# ─────────────────────────────────────────────────────────────
NAME_TO_SLUG = {
    "桐生":   "kiryu",    "戸田":   "toda",     "江戸川": "edogawa",
    "平和島": "heiwajima","多摩川": "tamagawa", "浜名湖": "hamanako",
    "蒲郡":   "gamagori", "常滑":   "tokoname", "津":     "tsu",
    "三国":   "mikuni",   "びわこ": "biwako",   "住之江": "suminoe",
    "尼崎":   "amagasaki","鳴門":   "naruto",   "丸亀":   "marugame",
    "児島":   "kojima",   "宮島":   "miyajima", "徳山":   "tokuyama",
    "下関":   "shimonoseki","若松":  "wakamatsu","芦屋":   "ashiya",
    "福岡":   "fukuoka",  "唐津":   "karatsu",  "大村":   "omura",
}

# デイリーループの開始時刻
DAILY_START_HOUR   = 8   # 8:00 に起動
DAILY_START_MINUTE = 0
CSV_RETRY_INTERVAL = 300  # CSVが無いとき5分ごとにリトライ
CSV_RETRY_LIMIT    = 60   # 最大60分（9:00）待つ


# ─────────────────────────────────────────────────────────────
# 時刻ユーティリティ
# ─────────────────────────────────────────────────────────────
def next_start_time(hour: int = DAILY_START_HOUR,
                    minute: int = DAILY_START_MINUTE) -> datetime:
    """今日または翌日の HH:MM を返す（過去なら翌日）"""
    now = datetime.now()
    t = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if t <= now:
        t += timedelta(days=1)
    return t


def wait_until(target: datetime, label: str = ""):
    """target まで30秒おきに残り時間を表示しながら待機する"""
    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            break
        if remaining > 60:
            print(f"  [{label}] 待機中... あと {remaining/3600:.1f}時間 "
                  f"({target.strftime('%m/%d %H:%M')} 開始)", end="\r")
            time.sleep(30)
        else:
            time.sleep(remaining)
            break


# ─────────────────────────────────────────────────────────────
# CSVから会場・締め切り時刻を読み込む
# ─────────────────────────────────────────────────────────────
def load_venues_from_csv(csv_dir: Path, date_str: str) -> list:
    """
    csv_dir 内の {会場}_{日付}.csv を探して読み込み、
    会場ごとの締め切り時刻を返す。

    returns: [
        {
            "name": "びわこ",
            "slug": "biwako",
            "deadlines": {1: "10:36", 2: "11:03", ...}
        },
        ...
    ]
    """
    results = []
    csv_files = list(csv_dir.glob("*.csv"))

    if not csv_files:
        return []

    for csv_path in sorted(csv_files):
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str)
        except Exception as e:
            print(f"  [WARN] {csv_path.name} 読込失敗: {e}")
            continue

        # 必要な列が揃っているか確認
        required = {"会場", "日付", "レース", "締切時刻"}
        if not required.issubset(set(df.columns)):
            continue

        # 日付でフィルタ
        df["日付_norm"] = df["日付"].astype(str).str.replace("/", "-").str.strip()
        df_day = df[df["日付_norm"] == date_str]

        if df_day.empty:
            continue

        # 会場名取得
        venue_name = df_day["会場"].iloc[0].strip()
        slug = NAME_TO_SLUG.get(venue_name)
        if not slug:
            print(f"  [WARN] 未対応の会場名: {venue_name}（スラッグ不明）")
            continue

        # レースごとの締め切り時刻を取得（重複排除）
        race_dl = (
            df_day.drop_duplicates(subset=["レース"])
            .sort_values("レース")
        )
        deadlines = {}
        for _, row in race_dl.iterrows():
            try:
                race_no = int(str(row["レース"]).strip())
                dl_time = str(row["締切時刻"]).strip()
                if re.match(r"\d{1,2}:\d{2}", dl_time):
                    deadlines[race_no] = dl_time
            except Exception:
                continue

        if deadlines:
            results.append({
                "name":      venue_name,
                "slug":      slug,
                "deadlines": deadlines,
                "csv_path":  str(csv_path),
            })
            print(f"  ✓ {venue_name}: {len(deadlines)}R分"
                  f" ({deadlines[min(deadlines)]}〜{deadlines[max(deadlines)]})"
                  f"  [{csv_path.name}]")

    return results


# ─────────────────────────────────────────────────────────────
# CSVリトライ付き読み込み（デイリーループ用）
# ─────────────────────────────────────────────────────────────
def load_venues_with_retry(csv_dir: Path, date_str: str) -> list:
    """
    CSVが見つからない場合、CSV_RETRY_INTERVAL秒おきに
    CSV_RETRY_LIMIT分まで再試行する。
    """
    deadline = datetime.now() + timedelta(minutes=CSV_RETRY_LIMIT)
    attempt  = 0

    while True:
        attempt += 1
        venues = load_venues_from_csv(csv_dir, date_str)
        if venues:
            return venues

        remaining = (deadline - datetime.now()).total_seconds()
        if remaining <= 0:
            print(f"  [WARN] {CSV_RETRY_LIMIT}分待ってもCSVが見つかりませんでした。本日はスキップします。")
            return []

        print(f"  [CSV待機] {date_str} のCSVがまだありません。"
              f"{CSV_RETRY_INTERVAL//60}分後に再試行 "
              f"(残り{remaining/60:.0f}分) ...")
        time.sleep(CSV_RETRY_INTERVAL)


# ─────────────────────────────────────────────────────────────
# 1会場分のスレッド
# ─────────────────────────────────────────────────────────────
def venue_worker(venue_info: dict, date_str: str,
                 window_minutes: int, poll_interval: int,
                 out_dir: Path, results: dict, lock: threading.Lock):
    name = venue_info["name"]
    slug = venue_info["slug"]
    deadlines = venue_info["deadlines"]
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
        with lock:
            results[name] = "✓ 完了"
    except Exception as e:
        with lock:
            print(f"\n[{name}] エラー: {e}")
            results[name] = f"✗ エラー: {e}"


# ─────────────────────────────────────────────────────────────
# 1日分の実行
# ─────────────────────────────────────────────────────────────
def run_one_day(date_str: str, csv_dir: Path,
                window_minutes: int, poll_interval: int,
                out_dir: Path, use_retry: bool = False):
    """
    指定日のCSVを読んで全会場並列実行する。
    use_retry=True の場合、CSVが無ければリトライ待機する。
    """
    print("=" * 65)
    print(f"  テン展示 自動取得（CSV連携版）")
    print(f"  日付       : {date_str}")
    print(f"  CSVフォルダ: {csv_dir}")
    print(f"  ウィンドウ : 締め切り{window_minutes}分前〜締め切り時刻")
    print(f"  ポーリング : {poll_interval}秒ごと")
    print("=" * 65)

    if not csv_dir.exists():
        print(f"\n[ERROR] フォルダが見つかりません: {csv_dir}")
        return

    # CSVから会場・締め切り時刻を読み込み
    print(f"\n【Step1】{date_str} のCSVを読み込み中...")
    if use_retry:
        venues = load_venues_with_retry(csv_dir, date_str)
    else:
        venues = load_venues_from_csv(csv_dir, date_str)

    if not venues:
        print(f"\n[ERROR] {date_str} のデータが見つかりませんでした")
        print(f"  CSVフォルダ: {csv_dir}")
        print(f"  ファイル例: びわこ_{date_str}.csv")
        return

    print(f"\n対象: {len(venues)}会場")

    # 並列実行
    print(f"\n【Step2】{len(venues)}会場を並列実行開始\n")
    results = {}
    lock    = threading.Lock()
    threads = [
        threading.Thread(
            target=venue_worker,
            args=(v, date_str, window_minutes, poll_interval,
                  out_dir, results, lock),
            name=v["name"],
            daemon=True,
        )
        for v in venues
    ]
    for t in threads:
        t.start()
        time.sleep(0.3)

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n\n[終了] 中断されました")
        return

    # サマリー
    print(f"\n{'='*65}")
    print("  完了サマリー")
    print("=" * 65)
    for name, status in results.items():
        print(f"  {name}: {status}")
    print(f"\n  テン展示データ保存先: {out_dir or '（保存なし）'}")


# ─────────────────────────────────────────────────────────────
# デイリーループ
# ─────────────────────────────────────────────────────────────
def run_daily_loop(csv_dir: Path, window_minutes: int,
                   poll_interval: int, out_dir: Path):
    """
    毎朝 DAILY_START_HOUR:DAILY_START_MINUTE に起動するループ。
    プロセスを起動したまま連日動かし続ける。
    起動時刻が既に DAILY_START_HOUR を過ぎていれば待機せず即実行する。
    """
    day_count = 0
    first_iteration = True  # ★ 初回フラグ

    while True:
        now = datetime.now()

        # ★ 修正: 初回かつ今日の開始時刻を過ぎていれば待機せず即実行
        today_start = now.replace(
            hour=DAILY_START_HOUR, minute=DAILY_START_MINUTE,
            second=0, microsecond=0
        )
        if first_iteration and now >= today_start:
            # 既に8:00を過ぎているので今日分を即実行（待機スキップ）
            print(f"\n{'='*65}")
            print(f"  [デイリーループ] 起動時刻 {now.strftime('%H:%M')} は"
                  f" {DAILY_START_HOUR:02d}:{DAILY_START_MINUTE:02d} 以降のため"
                  f" 今日分を即実行します")
            print(f"{'='*65}")
        else:
            # ── 次の8:00まで待機 ──────────────────────────
            start_dt = next_start_time(DAILY_START_HOUR, DAILY_START_MINUTE)
            if (start_dt - now).total_seconds() > 60:
                print(f"\n{'='*65}")
                print(f"  [デイリーループ] 次回起動: {start_dt.strftime('%Y/%m/%d %H:%M')}")
                print(f"{'='*65}")
                wait_until(start_dt, label="デイリーループ")

        first_iteration = False  # ★ 2回目以降は通常の待機ロジックへ

        # ── 本日の日付で実行 ──────────────────────────
        day_count += 1
        date_str = date_cls.today().strftime("%Y-%m-%d")
        print(f"\n\n{'#'*65}")
        print(f"  デイリーループ {day_count}日目: {date_str}")
        print(f"{'#'*65}\n")

        try:
            run_one_day(
                date_str=date_str,
                csv_dir=csv_dir,
                window_minutes=window_minutes,
                poll_interval=poll_interval,
                out_dir=out_dir,
                use_retry=True,   # CSVが来るまでリトライ
            )
        except KeyboardInterrupt:
            print("\n\n[デイリーループ終了] ユーザーによる中断")
            return
        except Exception as e:
            print(f"\n[ERROR] 予期しないエラー: {e}")
            print("  → 翌日8:00に再試行します")

        print(f"\n  本日({date_str})の処理が完了しました。翌日8:00まで待機します。")


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="既存CSVから締め切り時刻を読んでテン展示を自動取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--csv-dir",
        default=r"C:\Users\user\Desktop\データ収集\scripts\csv_output",
        help="CSVフォルダのパス")
    ap.add_argument("--date", default=None,
        help="日付 YYYY-MM-DD（指定するとその1日だけ実行して終了。省略でデイリーループモード）")
    ap.add_argument("--window-minutes", type=int, default=25,
        help="締め切り何分前から取得開始するか（デフォルト: 25）")
    ap.add_argument("--poll-interval", type=int, default=60,
        help="ポーリング間隔(秒)（デフォルト: 60）")
    ap.add_argument("--out", default=r"C:\Users\user\Desktop\データ収集\scripts\tenji_data",
        help="テン展示データの保存先（デフォルト: tenji_data）")
    ap.add_argument("--no-save", action="store_true", help="保存しない")
    args = ap.parse_args()

    csv_dir = Path(args.csv_dir)
    out_dir = None if args.no_save else Path(args.out)

    if args.date:
        # ── 日付指定: 1日だけ実行して終了（従来動作）──
        run_one_day(
            date_str=args.date,
            csv_dir=csv_dir,
            window_minutes=args.window_minutes,
            poll_interval=args.poll_interval,
            out_dir=out_dir,
            use_retry=False,
        )
    else:
        # ── デイリーループモード ──
        print(f"\n{'='*65}")
        print(f"  テン展示 デイリーループモード起動")
        print(f"  毎朝 {DAILY_START_HOUR:02d}:{DAILY_START_MINUTE:02d} に自動実行します")
        print(f"  CSVがない場合は最大{CSV_RETRY_LIMIT}分リトライします")
        print(f"  終了するには Ctrl+C を押してください")
        print(f"{'='*65}")

        try:
            run_daily_loop(
                csv_dir=csv_dir,
                window_minutes=args.window_minutes,
                poll_interval=args.poll_interval,
                out_dir=out_dir,
            )
        except KeyboardInterrupt:
            print("\n\n[終了] デイリーループを停止しました")


if __name__ == "__main__":
    main()
