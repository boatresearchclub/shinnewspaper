"""
result_from_csv.py  —  CSVの締め切り時刻を読んで締め切り+N分後に結果を自動取得
=================================================================================
【使い方】

  # デイリーループモード（毎日8:00に自動起動）
  python result_from_csv.py

  # フォルダ・遅延分数を指定
  python result_from_csv.py --csv-dir "C:/Users/user/Desktop/データ収集/scripts/csv_output" --delay 20

  # 日付を指定（その1日だけ実行して終了）
  python result_from_csv.py --date 2026-06-11

【動作】
  1. csv_output フォルダ内の当日CSV（{会場}_{日付}.csv）を全部読む
  2. 各CSVから「会場スラッグ」と「レースごとの締切時刻」を取得
  3. 各レースの「締め切り時刻 + delay分」になったら fetch_result() を呼ぶ
  4. 3連単が取れるまで poll_interval 秒おきにリトライ（最大 max_retry 回）
  5. 全レース完了 or タイムアウト後、翌日8:00まで待機 → 繰り返し

依存:
  pip install requests beautifulsoup4 pandas
  ※ fetch_result.py と同じフォルダに置くこと
"""

import argparse
import threading
import time
from datetime import datetime, timedelta, date as date_cls
from pathlib import Path

import pandas as pd

from fetch_result import fetch_result, VENUE_JCD, VENUE_JA

# ─────────────────────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────────────────────
DAILY_START_HOUR   = 8
DAILY_START_MINUTE = 0
CSV_RETRY_INTERVAL = 300   # CSVが無いとき5分ごとにリトライ
CSV_RETRY_LIMIT    = 60    # 最大60分待つ

DEFAULT_DELAY_MINUTES = 20   # 締め切り後何分で取得開始するか（--delay で変更可）
POLL_INTERVAL_SEC     = 60   # 結果未確定時のリトライ間隔（秒）
MAX_RETRY             = 30   # 最大リトライ回数（30回×60秒 = 30分）

# 会場名 → スラッグ（CSVの「会場」列と対応）
NAME_TO_SLUG = {v: k for k, v in VENUE_JA.items()}   # VENUE_JAの逆引き
# VENUE_JAに無い会場はVENUE_JCDのslug→jcdから補完不要（VENUE_JAで全24場網羅済み）


# ─────────────────────────────────────────────────────────────
# 時刻ユーティリティ
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
# CSVから会場・締め切り時刻を読み込む
# ─────────────────────────────────────────────────────────────
def load_venues_from_csv(csv_dir: Path, date_str: str) -> list:
    """
    csv_dir 内の *.csv を読み込み、会場ごとの情報を返す。

    returns: [
        {
            "name":      "常滑",
            "slug":      "tokoname",
            "date_nd":   "20260611",
            "deadlines": {1: datetime(2026,6,11,10,36), 2: datetime(...), ...}
        },
        ...
    ]
    """
    import re
    results  = []
    csv_files = list(csv_dir.glob("*.csv"))
    if not csv_files:
        return []

    date_nd = date_str.replace("-", "")   # "YYYY-MM-DD" → "YYYYMMDD"

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
        slug = NAME_TO_SLUG.get(venue_name)
        if not slug:
            print(f"  [WARN] 未対応の会場名: {venue_name}（スラッグ不明）", flush=True)
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
                    h, m = map(int, dl_time.split(":"))
                    dl_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=h, minute=m)
                    deadlines[race_no] = dl_dt
            except Exception:
                continue

        if deadlines:
            results.append({
                "name":      venue_name,
                "slug":      slug,
                "date_nd":   date_nd,
                "deadlines": deadlines,
            })
            dl_vals = [v.strftime("%H:%M") for v in deadlines.values()]
            print(f"  ✓ {venue_name}: {len(deadlines)}R分"
                  f" ({dl_vals[0]}〜{dl_vals[-1]})"
                  f"  [{csv_path.name}]", flush=True)

    return results


def load_venues_with_retry(csv_dir: Path, date_str: str) -> list:
    deadline = datetime.now() + timedelta(minutes=CSV_RETRY_LIMIT)
    while True:
        venues = load_venues_from_csv(csv_dir, date_str)
        if venues:
            return venues
        remaining = (deadline - datetime.now()).total_seconds()
        if remaining <= 0:
            print(f"  [WARN] {CSV_RETRY_LIMIT}分待ってもCSVが見つかりませんでした。本日はスキップします。",
                  flush=True)
            return []
        print(f"  [CSV待機] {date_str} のCSVがまだありません。"
              f"{CSV_RETRY_INTERVAL//60}分後に再試行 (残り{remaining/60:.0f}分) ...",
              flush=True)
        time.sleep(CSV_RETRY_INTERVAL)


# ─────────────────────────────────────────────────────────────
# 1会場分のワーカースレッド
# ─────────────────────────────────────────────────────────────
def venue_worker(venue: dict, delay_minutes: int, out_dir: Path,
                 results: dict, lock: threading.Lock):
    """
    各レースの「締め切り時刻 + delay_minutes分」になったら結果取得を試みる。
    3連単が取れるまで POLL_INTERVAL_SEC 秒おきにリトライ（最大 MAX_RETRY 回）。
    """
    name     = venue["name"]
    slug     = venue["slug"]
    date_nd  = venue["date_nd"]
    deadlines = venue["deadlines"]   # {rno: datetime}

    completed = {}   # {rno: True}

    for rno in sorted(deadlines.keys()):
        dl_dt       = deadlines[rno]
        fetch_start = dl_dt + timedelta(minutes=delay_minutes)

        # 取得開始時刻まで待機
        now = datetime.now()
        if fetch_start > now:
            wait_sec = (fetch_start - now).total_seconds()
            print(f"  [{name} R{rno}] 結果取得待機: {fetch_start.strftime('%H:%M')} まで"
                  f"（あと{wait_sec/60:.0f}分）", flush=True)
            time.sleep(wait_sec)

        # リトライループ
        for attempt in range(1, MAX_RETRY + 1):
            print(f"  [{name} R{rno}] 結果取得試行 {attempt}/{MAX_RETRY}", flush=True)
            try:
                ok = fetch_result(slug, date_nd, rno, out_dir)
            except Exception as e:
                print(f"  [{name} R{rno}] エラー: {e}", flush=True)
                ok = False

            if ok:
                print(f"  ✅ [{name} R{rno}] 取得完了", flush=True)
                completed[rno] = True
                time.sleep(2.0)   # 連続リクエスト抑制
                break
            else:
                if attempt < MAX_RETRY:
                    print(f"  [{name} R{rno}] 未確定 → {POLL_INTERVAL_SEC}秒後リトライ",
                          flush=True)
                    time.sleep(POLL_INTERVAL_SEC)
                else:
                    print(f"  ⚠ [{name} R{rno}] {MAX_RETRY}回リトライ失敗 → スキップ",
                          flush=True)

    with lock:
        results[name] = f"✓ {len(completed)}/{len(deadlines)}R 完了"


# ─────────────────────────────────────────────────────────────
# 1日分の実行
# ─────────────────────────────────────────────────────────────
def run_one_day(date_str: str, csv_dir: Path, delay_minutes: int,
                out_dir: Path, use_retry: bool = False):
    print("=" * 65, flush=True)
    print(f"  結果 自動取得（CSV連携版）", flush=True)
    print(f"  日付       : {date_str}", flush=True)
    print(f"  CSVフォルダ: {csv_dir}", flush=True)
    print(f"  取得開始   : 締め切り + {delay_minutes}分後", flush=True)
    print("=" * 65, flush=True)

    if not csv_dir.exists():
        print(f"\n[ERROR] フォルダが見つかりません: {csv_dir}", flush=True)
        return

    print(f"\n【Step1】{date_str} のCSVを読み込み中...", flush=True)
    if use_retry:
        venues = load_venues_with_retry(csv_dir, date_str)
    else:
        venues = load_venues_from_csv(csv_dir, date_str)

    if not venues:
        print(f"\n[ERROR] {date_str} のデータが見つかりませんでした", flush=True)
        return

    print(f"\n対象: {len(venues)}会場", flush=True)
    print(f"\n【Step2】{len(venues)}会場を並列実行開始\n", flush=True)

    thread_results = {}
    lock    = threading.Lock()
    threads = [
        threading.Thread(
            target=venue_worker,
            args=(v, delay_minutes, out_dir, thread_results, lock),
            name=v["name"],
            daemon=True,
        )
        for v in venues
    ]
    for t in threads:
        t.start()
        time.sleep(0.2)

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n\n[終了] 中断されました", flush=True)
        return

    print(f"\n{'='*65}", flush=True)
    print("  完了サマリー", flush=True)
    print("=" * 65, flush=True)
    for name, status in thread_results.items():
        print(f"  {name}: {status}", flush=True)
    print(f"\n  結果データ保存先: {out_dir}", flush=True)


# ─────────────────────────────────────────────────────────────
# デイリーループ
# ─────────────────────────────────────────────────────────────
def run_daily_loop(csv_dir: Path, delay_minutes: int, out_dir: Path):
    day_count      = 0
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
                delay_minutes=delay_minutes,
                out_dir=out_dir,
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
        description="CSVの締め切り時刻を読んで締め切り+N分後に結果を自動取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--csv-dir",
        default=r"C:\Users\user\Desktop\データ収集\scripts\csv_output",
        help="CSVフォルダのパス")
    ap.add_argument("--date", default=None,
        help="日付 YYYY-MM-DD（指定するとその1日だけ実行して終了。省略でデイリーループモード）")
    ap.add_argument("--delay", type=int, default=DEFAULT_DELAY_MINUTES,
        help=f"締め切り後何分で結果取得を開始するか（デフォルト: {DEFAULT_DELAY_MINUTES}）")
    ap.add_argument("--out",
        default=r"C:\Users\user\Desktop\データ収集\scripts\result_data",
        help="結果データの保存先")
    args = ap.parse_args()

    csv_dir = Path(args.csv_dir)
    out_dir = Path(args.out)

    if args.date:
        run_one_day(
            date_str=args.date,
            csv_dir=csv_dir,
            delay_minutes=args.delay,
            out_dir=out_dir,
            use_retry=False,
        )
    else:
        print(f"\n{'='*65}", flush=True)
        print(f"  結果取得 デイリーループモード起動", flush=True)
        print(f"  毎朝 {DAILY_START_HOUR:02d}:{DAILY_START_MINUTE:02d} に自動実行します", flush=True)
        print(f"  締め切り + {args.delay}分後に結果取得開始", flush=True)
        print(f"  CSVがない場合は最大{CSV_RETRY_LIMIT}分リトライします", flush=True)
        print(f"  終了するには Ctrl+C を押してください", flush=True)
        print(f"{'='*65}", flush=True)

        try:
            run_daily_loop(
                csv_dir=csv_dir,
                delay_minutes=args.delay,
                out_dir=out_dir,
            )
        except KeyboardInterrupt:
            print("\n\n[終了] デイリーループを停止しました", flush=True)


if __name__ == "__main__":
    main()
