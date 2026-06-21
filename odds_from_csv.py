"""
odds_from_csv.py  —  既存CSVから締め切り時刻・会場を読んでオッズを自動取得
=============================================================================
【使い方】

  # デイリーループモード（毎日8:00に自動起動）
  python odds_from_csv.py

  # フォルダを指定
  python odds_from_csv.py --csv-dir "C:/Users/user/Desktop/データ収集/scripts/csv_output"

  # 日付を指定（その1日だけ実行して終了）
  python odds_from_csv.py --date 2026-06-11

【動作】
  1. csv_output フォルダ内の当日CSV（{会場}_{日付}.csv）を全部読む
  2. 各CSVから「会場名」と「レースごとの締切時刻」を取得
  3. fetch_odds.fetch_all_races() に deadline_map を渡して常駐取得ループへ

  --date 省略時はデイリーループモード:
    - 毎朝8:00にCSVを読み込み → 全レース取得ループ
    - 全レース完了後、翌日8:00まで待機 → 繰り返し
    - 8:00時点でCSVがまだ無ければ5分おきにリトライ（最大9:00まで）

依存:
  pip install beautifulsoup4 pandas
  ※ fetch_odds.py と同じフォルダに置くこと
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, date as date_cls
from pathlib import Path

import pandas as pd

from fetch_odds import (
    fetch_all_races,
    VENUE_JCD,
    VENUE_SLUG,
    ODDS_DIR,
)

# ─────────────────────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────────────────────
DAILY_START_HOUR   = 8
DAILY_START_MINUTE = 0
CSV_RETRY_INTERVAL = 300   # CSVが無いとき5分ごとにリトライ
CSV_RETRY_LIMIT    = 60    # 最大60分（9:00）待つ

# 会場名 → 場コード（fetch_odds.VENUE_JCD と同一だが、CSVの「会場」列照合用に別名定義）
NAME_TO_JCD  = VENUE_JCD
NAME_TO_SLUG = VENUE_SLUG


# ─────────────────────────────────────────────────────────────
# 時刻ユーティリティ（tenji_from_csv.py と同一）
# ─────────────────────────────────────────────────────────────
def next_start_time(hour: int = DAILY_START_HOUR,
                    minute: int = DAILY_START_MINUTE) -> datetime:
    now = datetime.now()
    t = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if t <= now:
        t += timedelta(days=1)
    return t


def wait_until(target: datetime, label: str = ""):
    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            break
        if remaining > 60:
            print(f"  [{label}] 待機中... あと {remaining/3600:.1f}時間 "
                  f"({target.strftime('%m/%d %H:%M')} 開始)", end="\r", flush=True)
            time.sleep(30)
        else:
            time.sleep(remaining)
            break


# ─────────────────────────────────────────────────────────────
# CSVから会場・締め切り時刻を読み込む（tenji_from_csv.py と同一ロジック）
# ─────────────────────────────────────────────────────────────
def load_venues_from_csv(csv_dir: Path, date_str: str) -> list:
    """
    csv_dir 内の *.csv を読み込み、venues_dict と deadline_map を返す。

    returns: (venues_dict, deadline_map)
      venues_dict  : {"びわこ": "2026-06-11", "常滑": "2026-06-11", ...}
      deadline_map : {"びわこ": {1: "10:36", 2: "11:03", ...}, ...}
    """
    import re
    venues_dict  = {}
    deadline_map = {}

    csv_files = list(csv_dir.glob("*.csv"))
    if not csv_files:
        return {}, {}

    for csv_path in sorted(csv_files):
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str)
        except Exception as e:
            print(f"  [WARN] {csv_path.name} 読込失敗: {e}", flush=True)
            continue

        required = {"会場", "日付", "レース", "締切時刻"}
        if not required.issubset(set(df.columns)):
            continue

        df["日付_norm"] = df["日付"].astype(str).str.replace("/", "-").str.strip()
        df_day = df[df["日付_norm"] == date_str]
        if df_day.empty:
            continue

        venue_name = df_day["会場"].iloc[0].strip()
        if venue_name not in NAME_TO_JCD:
            print(f"  [WARN] 未対応の会場名: {venue_name}（場コード不明）", flush=True)
            continue

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
            venues_dict[venue_name]  = date_str
            deadline_map[venue_name] = deadlines
            dl_vals = list(deadlines.values())
            print(f"  ✓ {venue_name}: {len(deadlines)}R分"
                  f" ({dl_vals[0]}〜{dl_vals[-1]})"
                  f"  [{csv_path.name}]", flush=True)

    return venues_dict, deadline_map


def load_venues_with_retry(csv_dir: Path, date_str: str) -> tuple:
    """CSVが見つからない場合にリトライ付きで読み込む"""
    deadline = datetime.now() + timedelta(minutes=CSV_RETRY_LIMIT)
    attempt  = 0

    while True:
        attempt += 1
        venues_dict, deadline_map = load_venues_from_csv(csv_dir, date_str)
        if venues_dict:
            return venues_dict, deadline_map

        remaining = (deadline - datetime.now()).total_seconds()
        if remaining <= 0:
            print(f"  [WARN] {CSV_RETRY_LIMIT}分待ってもCSVが見つかりませんでした。本日はスキップします。",
                  flush=True)
            return {}, {}

        print(f"  [CSV待機] {date_str} のCSVがまだありません。"
              f"{CSV_RETRY_INTERVAL//60}分後に再試行 "
              f"(残り{remaining/60:.0f}分) ...", flush=True)
        time.sleep(CSV_RETRY_INTERVAL)


# ─────────────────────────────────────────────────────────────
# 1日分の取得ループ
# ─────────────────────────────────────────────────────────────
def run_one_day(date_str: str, csv_dir: Path, use_retry: bool = False):
    """
    指定日のCSVを読んで fetch_all_races() の取得ループを回す。
    fetch_all_races() は (saved, next_wait_sec, has_active) を返すので、
    has_active が False になるまでここでループを管理する。
    """
    print("=" * 65, flush=True)
    print(f"  オッズ 自動取得（CSV連携版）", flush=True)
    print(f"  日付       : {date_str}", flush=True)
    print(f"  CSVフォルダ: {csv_dir}", flush=True)
    print("=" * 65, flush=True)

    if not csv_dir.exists():
        print(f"\n[ERROR] フォルダが見つかりません: {csv_dir}", flush=True)
        return

    print(f"\n【Step1】{date_str} のCSVを読み込み中...", flush=True)
    if use_retry:
        venues_dict, deadline_map = load_venues_with_retry(csv_dir, date_str)
    else:
        venues_dict, deadline_map = load_venues_from_csv(csv_dir, date_str)

    if not venues_dict:
        print(f"\n[ERROR] {date_str} のデータが見つかりませんでした", flush=True)
        return

    print(f"\n対象: {len(venues_dict)}会場", flush=True)
    print(f"\n【Step2】オッズ取得ループ開始\n", flush=True)

    total_saved = []

    while True:
        try:
            saved, next_wait_sec, has_active = fetch_all_races(
                venues_dict=venues_dict,
                deadline_map=deadline_map,
                verbose=True,
            )
            total_saved.extend(saved)

            if not has_active:
                break

            if next_wait_sec > 0:
                time.sleep(next_wait_sec)

        except KeyboardInterrupt:
            print("\n\n[終了] 中断されました", flush=True)
            break
        except Exception as e:
            print(f"\n[ERROR] 取得中に例外: {e} → 60秒後リトライ", flush=True)
            time.sleep(60)

    print(f"\n{'='*65}", flush=True)
    print(f"  完了: {len(total_saved)}ファイル保存", flush=True)
    print(f"  保存先: {ODDS_DIR}", flush=True)


# ─────────────────────────────────────────────────────────────
# デイリーループ（tenji_from_csv.py と同一構造）
# ─────────────────────────────────────────────────────────────
def run_daily_loop(csv_dir: Path):
    day_count     = 0
    first_iteration = True

    while True:
        now = datetime.now()
        today_start = now.replace(
            hour=DAILY_START_HOUR, minute=DAILY_START_MINUTE,
            second=0, microsecond=0
        )

        if first_iteration and now >= today_start:
            print(f"\n{'='*65}", flush=True)
            print(f"  [デイリーループ] 起動時刻 {now.strftime('%H:%M')} は"
                  f" {DAILY_START_HOUR:02d}:{DAILY_START_MINUTE:02d} 以降のため"
                  f" 今日分を即実行します", flush=True)
            print(f"{'='*65}", flush=True)
        else:
            start_dt = next_start_time(DAILY_START_HOUR, DAILY_START_MINUTE)
            if (start_dt - now).total_seconds() > 60:
                print(f"\n{'='*65}", flush=True)
                print(f"  [デイリーループ] 次回起動: {start_dt.strftime('%Y/%m/%d %H:%M')}",
                      flush=True)
                print(f"{'='*65}", flush=True)
                wait_until(start_dt, label="デイリーループ")

        first_iteration = False

        day_count += 1
        date_str = date_cls.today().strftime("%Y-%m-%d")
        print(f"\n\n{'#'*65}", flush=True)
        print(f"  デイリーループ {day_count}日目: {date_str}", flush=True)
        print(f"{'#'*65}\n", flush=True)

        try:
            run_one_day(
                date_str=date_str,
                csv_dir=csv_dir,
                use_retry=True,
            )
        except KeyboardInterrupt:
            print("\n\n[デイリーループ終了] ユーザーによる中断", flush=True)
            return
        except Exception as e:
            print(f"\n[ERROR] 予期しないエラー: {e}", flush=True)
            print("  → 翌日8:00に再試行します", flush=True)

        print(f"\n  本日({date_str})の処理が完了しました。翌日8:00まで待機します。",
              flush=True)


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="既存CSVから締め切り時刻を読んでオッズを自動取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--csv-dir",
        default=r"C:\Users\user\Desktop\データ収集\scripts\csv_output",
        help="CSVフォルダのパス")
    ap.add_argument("--date", default=None,
        help="日付 YYYY-MM-DD（指定するとその1日だけ実行して終了。省略でデイリーループモード）")
    args = ap.parse_args()

    csv_dir = Path(args.csv_dir)

    if args.date:
        run_one_day(
            date_str=args.date,
            csv_dir=csv_dir,
            use_retry=False,
        )
    else:
        print(f"\n{'='*65}", flush=True)
        print(f"  オッズ デイリーループモード起動", flush=True)
        print(f"  毎朝 {DAILY_START_HOUR:02d}:{DAILY_START_MINUTE:02d} に自動実行します", flush=True)
        print(f"  CSVがない場合は最大{CSV_RETRY_LIMIT}分リトライします", flush=True)
        print(f"  終了するには Ctrl+C を押してください", flush=True)
        print(f"{'='*65}", flush=True)

        try:
            run_daily_loop(csv_dir=csv_dir)
        except KeyboardInterrupt:
            print("\n\n[終了] デイリーループを停止しました", flush=True)


if __name__ == "__main__":
    main()
