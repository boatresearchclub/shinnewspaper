"""
main_loop.py  —  テン展示・オッズ・結果・コメントを1プロセスで統合取得
========================================================================
【使い方】

  # デイリーループモード（毎日8:00に自動起動）
  python main_loop.py

  # 日付を指定（その1日だけ実行して終了）
  python main_loop.py --date 2026-06-14

  # CSVフォルダを指定
  python main_loop.py --csv-dir "C:/Users/user/Desktop/データ収集/scripts/csv_output"

  # 個別タスクだけ無効化
  python main_loop.py --no-tenji
  python main_loop.py --no-odds
  python main_loop.py --no-result
  python main_loop.py --no-comments

【変更前との違い】
  変更前: tenji_from_csv.py / odds_from_csv.py / result_from_csv.py / scrape_comments.py
          → 4プロセスが独立して動いていた（CPU・メモリを4倍消費）

  変更後: main_loop.py 1本
          → Pythonスレッドで並行実行（プロセスは1つ・メモリ大幅削減）
          → time.sleep中はCPUをほぼ使わない
          → どれか1つが落ちても他は継続（スレッド独立）
          → ログが1か所に集約される

【動作の詳細】
  毎朝8:00にCSVを読み込み、以下を並行して走らせる:

    スレッド1 [テン展示]  締め切り25分前〜締め切りまで取得
    スレッド2 [オッズ]    締め切りの1レース前から〜締め切りまで取得
    スレッド3 [結果]      締め切り後20分から取得（確定まで最大30分リトライ）
    スレッド4 [コメント]  締め切り20分前〜締め切りまで取得

  全スレッドが終わったら翌日8:00まで待機 → 繰り返し

依存（元のスクリプトと同じ）:
  pip install beautifulsoup4 pandas requests playwright
  playwright install chromium
  ※ このファイルを他のスクリプトと同じフォルダに置くこと
"""

from __future__ import annotations

import argparse
import gc
import threading
import time
from datetime import datetime, timedelta, date as date_cls
from pathlib import Path

import pandas as pd

# ─────────────────────────────────────────────────────────────
# メモリ最適化設定
# ─────────────────────────────────────────────────────────────
# 会場ごとにスレッドが多数（最大24会場×4タスク）並行起動する設計のため、
# OSデフォルトのスレッドスタックサイズ（環境によって8MB等）だと
# スレッド数 × スタックサイズ で数百MB〜GB規模の予約メモリになりうる。
#
# 重要: fetch_tenji.py / scrape_comments.py 等の内部実装が Playwright
# (ブラウザ操作)を使っている場合、コールスタックが深くなることがあるため、
# 極端に小さい値（数百KB）は機能を壊すリスクがある。
# requests/BeautifulSoupのみの軽量なケースでも安全マージンを取り、
# 2MB（多くの環境のデフォルトの1/4〜1/2程度）に設定する。
# これなら通常のHTTP処理・Playwright経由の処理いずれでも安全に動作しつつ、
# スレッド数が多い本ツールの構成ではメモリ削減効果が出る。
#
# 注意: stack_size はこの呼び出し以降に「新しく作成される」スレッドにのみ
# 適用される。メインスレッドには影響しない。プラットフォームによっては
# 設定できない/制約がある場合があるため、失敗しても処理は継続できるよう
# ガードする。
try:
    threading.stack_size(2 * 1024 * 1024)  # 2MB
except (ValueError, RuntimeError):
    # 環境によっては設定できない/小さすぎる場合がある。デフォルトのまま続行。
    pass

DAILY_START_HOUR   = 8
DAILY_START_MINUTE = 0
CSV_RETRY_INTERVAL = 300   # CSVが無いとき5分ごとにリトライ
CSV_RETRY_LIMIT    = 60    # 最大60分（9:00）待つ

DEFAULT_CSV_DIR     = r"C:\Users\user\Desktop\データ収集\scripts\csv_output"
DEFAULT_TENJI_OUT   = r"C:\Users\user\Desktop\データ収集\scripts\tenji_data"
DEFAULT_RESULT_OUT  = r"C:\Users\user\Desktop\データ収集\scripts\result_data"

TENJI_WINDOW_MINUTES  = 25   # 締め切り何分前からテン展示取得開始
TENJI_POLL_INTERVAL   = 60   # テン展示ポーリング間隔（秒）
RESULT_DELAY_MINUTES  = 20   # 締め切り後何分で結果取得開始
RESULT_POLL_INTERVAL  = 60   # 結果ポーリング間隔（秒）
RESULT_MAX_RETRY      = 30   # 結果リトライ最大回数

# 会場名 → スラッグ（共通マスタ）
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


# ─────────────────────────────────────────────────────────────
# ログ出力（スレッド名付き・排他制御）
# ─────────────────────────────────────────────────────────────
_log_lock = threading.Lock()

def log(msg: str, tag: str = ""):
    now = datetime.now().strftime("%H:%M:%S")
    prefix = f"[{tag}]" if tag else ""
    with _log_lock:
        print(f"  {now} {prefix} {msg}", flush=True)


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
            with _log_lock:
                print(f"  [{label}] 待機中... あと {remaining/3600:.1f}時間 "
                      f"({target.strftime('%m/%d %H:%M')} 開始)", end="\r", flush=True)
            time.sleep(30)
        else:
            time.sleep(remaining)
            break


# ─────────────────────────────────────────────────────────────
# CSVから会場・締め切り時刻を読み込む（共通）
# ─────────────────────────────────────────────────────────────
def load_venues_from_csv(csv_dir: Path, date_str: str) -> list:
    """
    csv_dir 内の *.csv を読み込み、会場ごとの情報を返す。

    returns: [
        {
            "name":      "常滑",
            "slug":      "tokoname",
            "date_nd":   "20260614",
            "deadlines": {1: "10:36", 2: "11:03", ...}   # str形式
        },
        ...
    ]
    """
    import re
    results = []
    csv_files = list(csv_dir.glob("*.csv"))
    if not csv_files:
        return []

    date_nd = date_str.replace("-", "")

    for csv_path in sorted(csv_files):
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str)
        except Exception as e:
            log(f"{csv_path.name} 読込失敗: {e}", "CSV")
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
            log(f"未対応の会場名: {venue_name}（スラッグ不明）", "CSV")
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
            results.append({
                "name":      venue_name,
                "slug":      slug,
                "date_nd":   date_nd,
                "deadlines": deadlines,
            })
            dl_vals = list(deadlines.values())
            log(f"✓ {venue_name}: {len(deadlines)}R分 "
                f"({dl_vals[0]}〜{dl_vals[-1]}) [{csv_path.name}]", "CSV")

        # 1ファイル分のDataFrame群はここで使い終わり。
        # ループを抜けるまでローカル変数として残り続けるとピーク時メモリが
        # 積み上がるため、次のイテレーションを待たず明示的に解放する。
        # （結果はすでに results / deadlines に必要分だけコピー済みなので
        #   機能・出力内容には一切影響しない）
        del df, df_day, race_dl

    return results


def load_venues_with_retry(csv_dir: Path, date_str: str) -> list:
    deadline = datetime.now() + timedelta(minutes=CSV_RETRY_LIMIT)
    while True:
        venues = load_venues_from_csv(csv_dir, date_str)
        if venues:
            return venues
        remaining = (deadline - datetime.now()).total_seconds()
        if remaining <= 0:
            log(f"{CSV_RETRY_LIMIT}分待ってもCSVが見つかりませんでした。本日はスキップします。", "CSV")
            return []
        log(f"{date_str} のCSVがまだありません。"
            f"{CSV_RETRY_INTERVAL//60}分後に再試行 (残り{remaining/60:.0f}分) ...", "CSV")
        time.sleep(CSV_RETRY_INTERVAL)


# ─────────────────────────────────────────────────────────────
# タスク1: テン展示取得スレッド
# ─────────────────────────────────────────────────────────────
def task_tenji(venues: list, date_str: str,
               window_minutes: int, poll_interval: int, out_dir: Path):
    """tenji_from_csv.py の run_one_day() 相当"""
    try:
        from fetch_tenji import VENUE_SLUG as TENJI_SLUG
        from tenji_scheduler_v2 import run_scheduler
    except ImportError as e:
        log(f"インポート失敗（テン展示スキップ）: {e}", "TENJI")
        return

    tag = "TENJI"
    log(f"開始 ({len(venues)}会場)", tag)

    sub_threads = []
    sub_results = {}
    lock = threading.Lock()

    def _worker(v):
        name = v["name"]
        slug = v["slug"]
        deadlines = v["deadlines"]
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
                sub_results[name] = "✓ 完了"
                log(f"✓ {name} 完了", tag)
        except Exception as e:
            with lock:
                sub_results[name] = f"✗ エラー: {e}"
                log(f"✗ {name} エラー: {e}", tag)

    for v in venues:
        t = threading.Thread(target=_worker, args=(v,), name=f"tenji-{v['name']}", daemon=True)
        sub_threads.append(t)
        t.start()
        time.sleep(0.3)

    for t in sub_threads:
        t.join()

    # join済みのThreadオブジェクト参照を明示的に解放。
    # 24会場規模だとThreadオブジェクト自体は小さいが、関数を抜けるまで
    # リストが残ると、間接的に参照しているスレッドローカル状態の解放が
    # 遅れる可能性があるため早めに切る。
    sub_threads.clear()

    log(f"全会場完了: {sub_results}", tag)


# ─────────────────────────────────────────────────────────────
# タスク2: オッズ取得スレッド
# ─────────────────────────────────────────────────────────────
def task_odds(venues: list, date_str: str):
    """odds_from_csv.py の run_one_day() 相当"""
    try:
        from fetch_odds import fetch_all_races, VENUE_JCD, VENUE_SLUG, ODDS_DIR
    except ImportError as e:
        log(f"インポート失敗（オッズスキップ）: {e}", "ODDS")
        return

    tag = "ODDS"
    log(f"開始 ({len(venues)}会場)", tag)

    # deadline_map を構築（fetch_all_races に渡す形式）
    venues_dict  = {}
    deadline_map = {}
    for v in venues:
        name = v["name"]
        if name not in VENUE_JCD:
            log(f"未対応の会場: {name}", tag)
            continue
        venues_dict[name]  = date_str
        deadline_map[name] = v["deadlines"]

    if not venues_dict:
        log("有効な会場なし", tag)
        return

    # 全会場・全レースの最終締め切り時刻を計算
    last_deadline = None
    for v in venues:
        for dl_str in v["deadlines"].values():
            try:
                dt = datetime.strptime(f"{date_str} {dl_str}", "%Y-%m-%d %H:%M")
                if last_deadline is None or dt > last_deadline:
                    last_deadline = dt
            except ValueError:
                pass
    if last_deadline:
        log(f"本日の最終締め切り: {last_deadline.strftime('%H:%M')}", tag)

    total_saved = []
    while True:
        # 全レースの締め切りを過ぎていたら終了
        if last_deadline and datetime.now() > last_deadline:
            log("全レース締め切り済み。終了します。", tag)
            break

        try:
            saved, next_wait_sec, has_active = fetch_all_races(
                venues_dict=venues_dict,
                deadline_map=deadline_map,
                verbose=True,
            )
            total_saved.extend(saved)
            if not has_active:
                # fetch_all_races が終了と判断しても、締め切り前なら待機して再試行
                # （R1の30分前ルール等でスキップされた場合に対応）
                if last_deadline and datetime.now() < last_deadline:
                    log("取得対象なし（開始前または一時的）→ 60秒後に再確認", tag)
                    time.sleep(60)
                    continue
                break
            if next_wait_sec > 0:
                time.sleep(next_wait_sec)
        except Exception as e:
            log(f"取得中に例外: {e} → 60秒後リトライ", tag)
            time.sleep(60)

    log(f"完了: {len(total_saved)}ファイル保存", tag)

    # ── 個別JSONを data/odds_YYYYMMDD.json に統合 ──
    try:
        from merge_odds import merge, save
        date_nd = date_str.replace("-", "")
        merged  = merge(date_nd)
        if merged:
            out = save(merged, date_nd)
            log(f"統合完了 → {out.name}", tag)
        else:
            log("統合対象ファイルなし", tag)
    except Exception as e:
        log(f"merge_odds失敗: {e}", tag)


# ─────────────────────────────────────────────────────────────
# タスク3: 結果取得スレッド
# ─────────────────────────────────────────────────────────────
def task_result(venues: list, delay_minutes: int, out_dir: Path):
    """result_from_csv.py の run_one_day() 相当"""
    try:
        from fetch_result import fetch_result as _fetch_result
    except ImportError as e:
        log(f"インポート失敗（結果スキップ）: {e}", "RESULT")
        return

    tag = "RESULT"
    log(f"開始 ({len(venues)}会場)", tag)

    sub_threads = []
    sub_results = {}
    lock = threading.Lock()

    def _worker(v):
        name    = v["name"]
        slug    = v["slug"]
        date_nd = v["date_nd"]
        # deadlines: {rno: "HH:MM"} → datetimeに変換
        date_base = datetime.strptime(date_nd, "%Y%m%d")
        deadlines_dt = {}
        for rno, dl_str in v["deadlines"].items():
            h, m = map(int, dl_str.split(":"))
            deadlines_dt[rno] = date_base.replace(hour=h, minute=m)

        completed = {}
        for rno in sorted(deadlines_dt.keys()):
            dl_dt       = deadlines_dt[rno]
            fetch_start = dl_dt + timedelta(minutes=delay_minutes)

            now = datetime.now()
            if fetch_start > now:
                wait_sec = (fetch_start - now).total_seconds()
                log(f"[{name} R{rno}] 結果取得待機: {fetch_start.strftime('%H:%M')} まで"
                    f"（あと{wait_sec/60:.0f}分）", tag)
                time.sleep(wait_sec)

            for attempt in range(1, RESULT_MAX_RETRY + 1):
                try:
                    ok = _fetch_result(slug, date_nd, rno, out_dir)
                except Exception as e:
                    log(f"[{name} R{rno}] エラー: {e}", tag)
                    ok = False

                if ok:
                    log(f"✅ [{name} R{rno}] 取得完了", tag)
                    completed[rno] = True
                    time.sleep(2.0)
                    break
                else:
                    if attempt < RESULT_MAX_RETRY:
                        time.sleep(RESULT_POLL_INTERVAL)
                    else:
                        log(f"⚠ [{name} R{rno}] {RESULT_MAX_RETRY}回リトライ失敗 → スキップ", tag)

        with lock:
            sub_results[name] = f"✓ {len(completed)}/{len(deadlines_dt)}R 完了"

    for v in venues:
        t = threading.Thread(target=_worker, args=(v,), name=f"result-{v['name']}", daemon=True)
        sub_threads.append(t)
        t.start()
        time.sleep(0.2)

    for t in sub_threads:
        t.join()

    sub_threads.clear()

    log(f"全会場完了: {sub_results}", tag)

# ─────────────────────────────────────────────────────────────
# タスク4: コメント取得スレッド
# ─────────────────────────────────────────────────────────────
def task_comments(venues: list, date_str: str,
                  window_minutes: int, poll_interval: int):
    """scrape_comments.py の CSV連携部分相当"""
    try:
        # scrape_comments.py から実行ロジックをインポート
        from scrape_comments import run_venues_from_csv_data
    except ImportError:
        # 直接インポートできない場合のフォールバック
        _task_comments_fallback(venues, date_str, window_minutes, poll_interval)
        return

    tag = "COMMENT"
    log(f"開始 ({len(venues)}会場)", tag)
    try:
        run_venues_from_csv_data(
            venues=venues,
            date_str=date_str,
            window_minutes=window_minutes,
            poll_interval=poll_interval,
        )
    except Exception as e:
        log(f"エラー: {e}", tag)
    log("完了", tag)


def _task_comments_fallback(venues: list, date_str: str,
                             window_minutes: int, poll_interval: int):
    """
    scrape_comments.py に run_venues_from_csv_data() が無い場合のフォールバック。
    内部でサブプロセスを立てず、スレッドで直接 scrape_comments の関数を呼ぶ。
    """
    tag = "COMMENT"
    log(f"開始（フォールバックモード） ({len(venues)}会場)", tag)

    try:
        import scrape_comments as sc
    except ImportError as e:
        log(f"scrape_comments インポート失敗: {e}", tag)
        return

    sub_threads = []
    lock = threading.Lock()

    def _worker(v):
        name = v["name"]
        slug = v["slug"]
        deadlines = v["deadlines"]  # {rno: "HH:MM"}
        date_base = datetime.strptime(date_str, "%Y-%m-%d")

        for rno in sorted(deadlines.keys()):
            dl_str = deadlines[rno]
            h, m   = map(int, dl_str.split(":"))
            dl_dt  = date_base.replace(hour=h, minute=m)
            start  = dl_dt - timedelta(minutes=window_minutes)

            now = datetime.now()
            if start > now:
                wait_sec = (start - now).total_seconds()
                log(f"[{name} R{rno}] コメント待機 {start.strftime('%H:%M')} まで", tag)
                time.sleep(wait_sec)

            # 締め切りまでポーリング
            while datetime.now() < dl_dt:
                try:
                    # scrape_comments の会場別スクレイパーを直接呼ぶ
                    scrapers = getattr(sc, "VENUE_SCRAPERS", {})
                    if slug in scrapers:
                        result = scrapers[slug](rno, date_str)
                        if result:
                            sc._save_comment(slug, date_str, rno, result)
                            log(f"✓ [{name} R{rno}] コメント取得", tag)
                            break
                except Exception as e:
                    log(f"[{name} R{rno}] コメントエラー: {e}", tag)

                time.sleep(poll_interval)

    for v in venues:
        t = threading.Thread(target=_worker, args=(v,), name=f"comment-{v['name']}", daemon=True)
        sub_threads.append(t)
        t.start()
        time.sleep(0.2)

    for t in sub_threads:
        t.join()

    sub_threads.clear()

    log("全会場完了", tag)


# ─────────────────────────────────────────────────────────────
# 1日分の実行（4タスクを並行起動）
# ─────────────────────────────────────────────────────────────
def run_one_day(date_str: str, csv_dir: Path,
                run_tenji:    bool = True,
                run_odds:     bool = True,
                run_result:   bool = True,
                run_comments: bool = True,
                tenji_out:    Path = None,
                result_out:   Path = None,
                use_retry:    bool = False):
    """
    4つのタスクをスレッドで並行実行する。
    全スレッドが終わるまでここでブロックする。
    """
    print("=" * 65, flush=True)
    print(f"  統合 自動取得ループ", flush=True)
    print(f"  日付       : {date_str}", flush=True)
    print(f"  CSVフォルダ: {csv_dir}", flush=True)
    active = [n for n, f in [("テン展示", run_tenji), ("オッズ", run_odds),
                               ("結果", run_result), ("コメント", run_comments)] if f]
    print(f"  有効タスク : {' / '.join(active)}", flush=True)
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
    print(f"\n【Step2】並行実行開始\n", flush=True)

    # ── 4タスクをメインスレッドから並行起動 ──────────────────
    task_threads = []

    if run_tenji:
        t = threading.Thread(
            target=task_tenji,
            args=(venues, date_str, TENJI_WINDOW_MINUTES, TENJI_POLL_INTERVAL, tenji_out),
            name="task-tenji",
            daemon=True,
        )
        task_threads.append(t)

    if run_odds:
        t = threading.Thread(
            target=task_odds,
            args=(venues, date_str),
            name="task-odds",
            daemon=True,
        )
        task_threads.append(t)

    if run_result:
        t = threading.Thread(
            target=task_result,
            args=(venues, RESULT_DELAY_MINUTES, result_out),
            name="task-result",
            daemon=True,
        )
        task_threads.append(t)

    if run_comments:
        t = threading.Thread(
            target=task_comments,
            args=(venues, date_str, 20, TENJI_POLL_INTERVAL),
            name="task-comments",
            daemon=True,
        )
        task_threads.append(t)

    for t in task_threads:
        t.start()

    try:
        for t in task_threads:
            t.join()
    except KeyboardInterrupt:
        print("\n\n[終了] 中断されました", flush=True)
        return
    finally:
        # この日の task_threads / venues はもう使わない。
        # デイリーループでは同じプロセスが翌日も使い回されるため、
        # ここで参照を切って明示的にGCを走らせ、次の日に持ち越す
        # メモリ（特にスレッド経由で積まれたオブジェクト群）を減らす。
        # KeyboardInterruptで早期returnする場合も含め必ず実行されるよう
        # finallyに置く。
        task_threads.clear()
        venues.clear()
        gc.collect()

    print(f"\n{'='*65}", flush=True)
    print(f"  本日({date_str})の全タスク完了", flush=True)


# ─────────────────────────────────────────────────────────────
# デイリーループ
# ─────────────────────────────────────────────────────────────
def run_daily_loop(csv_dir: Path,
                   run_tenji: bool = True,
                   run_odds: bool = True,
                   run_result: bool = True,
                   run_comments: bool = True,
                   tenji_out: Path = None,
                   result_out: Path = None):
    day_count = 0
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
                run_tenji=run_tenji,
                run_odds=run_odds,
                run_result=run_result,
                run_comments=run_comments,
                tenji_out=tenji_out,
                result_out=result_out,
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

        # 翌日8:00まで（通常23時間以上）の長い待機に入る前に、
        # この日処理した分のオブジェクトをまとめて回収しておく。
        # run_one_day側のfinallyで主要な参照は既に切れているが、
        # 例外系（run_one_day内で venues 構築中に例外が出た場合等）の
        # 取りこぼしも含めてここで一括して掃除する。
        gc.collect()


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="テン展示・オッズ・結果・コメントを1プロセスで統合取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--csv-dir", default=DEFAULT_CSV_DIR,
        help="CSVフォルダのパス")
    ap.add_argument("--date", default=None,
        help="日付 YYYY-MM-DD（指定するとその1日だけ実行して終了）")
    ap.add_argument("--tenji-out", default=DEFAULT_TENJI_OUT,
        help="テン展示データの保存先")
    ap.add_argument("--result-out", default=DEFAULT_RESULT_OUT,
        help="結果データの保存先")
    ap.add_argument("--no-tenji",    action="store_true", help="テン展示取得を無効化")
    ap.add_argument("--no-odds",     action="store_true", help="オッズ取得を無効化")
    ap.add_argument("--no-result",   action="store_true", help="結果取得を無効化")
    ap.add_argument("--no-comments", action="store_true", help="コメント取得を無効化")
    args = ap.parse_args()

    csv_dir    = Path(args.csv_dir)
    tenji_out  = Path(args.tenji_out)
    result_out = Path(args.result_out)

    print(f"\n{'='*65}", flush=True)
    print(f"  統合デイリーループ起動", flush=True)
    print(f"  毎朝 {DAILY_START_HOUR:02d}:{DAILY_START_MINUTE:02d} に自動実行します", flush=True)
    active = []
    if not args.no_tenji:    active.append("テン展示")
    if not args.no_odds:     active.append("オッズ")
    if not args.no_result:   active.append("結果")
    if not args.no_comments: active.append("コメント")
    print(f"  有効タスク : {' / '.join(active)}", flush=True)
    print(f"  終了するには Ctrl+C を押してください", flush=True)
    print(f"{'='*65}", flush=True)

    kwargs = dict(
        csv_dir=csv_dir,
        run_tenji=not args.no_tenji,
        run_odds=not args.no_odds,
        run_result=not args.no_result,
        run_comments=not args.no_comments,
        tenji_out=tenji_out,
        result_out=result_out,
    )

    try:
        if args.date:
            run_one_day(date_str=args.date, use_retry=False, **kwargs)
        else:
            run_daily_loop(**kwargs)
    except KeyboardInterrupt:
        print("\n\n[終了] 停止しました", flush=True)


if __name__ == "__main__":
    main()
