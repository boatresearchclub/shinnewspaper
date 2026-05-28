"""
fetch_tenji_history.py
======================
過去展示（テン展示）データを一括取得して tenji_data/ に保存するスクリプト。

【動作概要】
  1. csv_output/*.csv を走査して「会場 × 日付」の組み合わせを収集
  2. 各組み合わせで R1〜R12 の展示データを fetch_tenji.py 経由で取得
  3. tenji_data/tenji_{slug}_{YYYYMMDD}_R{XX}.json に保存（空データは保存しない）
  4. tenji_data/tenji_{slug}_{YYYYMMDD}.csv にも保存（fetch_tenji.py 準拠）
  5. 取得失敗・データなしレースは tenji_data/failed_races.json に記録
     → --retry で失敗分だけ再取得できる

【使い方】
  python fetch_tenji_history.py               # 対話式で指定
  python fetch_tenji_history.py --days 7      # 過去7日に絞る
  python fetch_tenji_history.py --date 20260515
  python fetch_tenji_history.py --from 20260501 --to 20260510
  python fetch_tenji_history.py --dry-run     # 取得せず対象一覧だけ表示
  python fetch_tenji_history.py --retry       # 前回失敗分のみ再取得
  python fetch_tenji_history.py --retry --dry-run  # 失敗リスト確認のみ

【注意】
  ・当日展示取得（auto_push.py 等）が動いている最中の実行は避けること。
    ファイルが壊れる恐れがあります。
  ・1レースあたりブラウザ取得（約10〜30秒）がかかります。
    会場ごとにブラウザを使い回すため、全件取得は時間がかかります。
  ・過去データはサイトに掲載されていない場合があります。
    その場合は空データで保存せず、failed_races.json に記録します。
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from itertools import groupby

import pandas as pd

# ── パス設定（fetch_tenji.py と同じ基準ディレクトリ）────────────────────────
SCRIPTS_DIR = Path(__file__).parent
CSV_DIR     = SCRIPTS_DIR / "csv_output"
TENJI_DIR   = SCRIPTS_DIR / "tenji_data"

HISTORY_DAYS   = 30
INTER_REQ_WAIT = 2.0   # レース間インターバル（秒）
FAILED_LIST    = "failed_races.json"  # tenji_data/ 以下に保存

# ── fetch_tenji.py をインポート ──────────────────────────────────────────────
try:
    from fetch_tenji import (
        VENUE_SLUG,
        BrowserSession,
        fetch_one,
    )
except ImportError:
    print("❌ fetch_tenji.py が見つかりません。同じフォルダに置いてください。")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# 日付セット生成（単日 / 範囲 / 過去N日）
# ─────────────────────────────────────────────────────────────────────────────

def build_target_dates(days: int | None = None,
                       date: str | None = None,
                       date_from: str | None = None,
                       date_to: str | None = None) -> set[str]:

    def normalize(d: str) -> str:
        d = d.strip().replace("/", "-")
        if len(d) == 8 and d.isdigit():
            return f"{d[:4]}-{d[4:6]}-{d[6:]}"
        return d

    today = datetime.now().date()

    # 単日指定
    if date:
        return {normalize(date)}

    # 範囲指定
    if date_from and date_to:
        start = datetime.strptime(normalize(date_from), "%Y-%m-%d").date()
        end   = datetime.strptime(normalize(date_to), "%Y-%m-%d").date()

        if start > end:
            raise ValueError("❌ --from は --to より前の日付にしてください")

        result = set()
        cur = start
        while cur <= end:
            result.add(cur.strftime("%Y-%m-%d"))
            cur += timedelta(days=1)
        return result

    # 過去days日（従来）
    if days is None:
        days = HISTORY_DAYS

    return {
        (today - timedelta(days=d)).strftime("%Y-%m-%d")
        for d in range(1, days + 1)
    }


# ─────────────────────────────────────────────────────────────────────────────
# 失敗リスト管理
# ─────────────────────────────────────────────────────────────────────────────

def load_failed_list() -> list[dict]:
    """tenji_data/failed_races.json を読み込む。なければ空リストを返す。"""
    path = TENJI_DIR / FAILED_LIST
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠ failed_races.json 読込失敗: {e}")
        return []


def save_failed_list(failed: list[dict]) -> None:
    """失敗リストを tenji_data/failed_races.json に保存する。"""
    TENJI_DIR.mkdir(exist_ok=True)
    path = TENJI_DIR / FAILED_LIST
    with open(path, "w", encoding="utf-8") as f:
        json.dump(failed, f, ensure_ascii=False, indent=2)
    print(f"\n  [失敗リスト] {len(failed)}件 → {path}", flush=True)


def add_failed(failed_list: list[dict],
               venue_name: str, slug: str, date_str: str, rno: int,
               reason: str) -> None:
    """失敗リストに1件追加（重複は上書き）。"""
    key = (slug, date_str, rno)
    # 既存エントリを削除してから追加（再試行時に reason を更新するため）
    failed_list[:] = [
        r for r in failed_list
        if not (r["slug"] == slug and r["date"] == date_str and r["race"] == rno)
    ]
    failed_list.append({
        "venue": venue_name,
        "slug":  slug,
        "date":  date_str,
        "race":  rno,
        "reason": reason,
        "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


def remove_succeeded(failed_list: list[dict],
                     slug: str, date_str: str, rno: int) -> None:
    """成功したレースを失敗リストから削除する。"""
    failed_list[:] = [
        r for r in failed_list
        if not (r["slug"] == slug and r["date"] == date_str and r["race"] == rno)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# CSV から「会場名 × 日付」組み合わせを収集
# ─────────────────────────────────────────────────────────────────────────────

def collect_venue_dates(target_dates: set[str]) -> list[tuple[str, str]]:
    """
    csv_output/*.csv を走査し、
    target_dates に含まれる日付の (会場名, "YYYY-MM-DD") ペアのリストを返す。
    """

    found: list[tuple[str, str]] = []
    seen: set[tuple[str, str]]   = set()

    for csv_path in sorted(glob.glob(str(CSV_DIR / "*.csv"))):
        fname = Path(csv_path).name

        matched_date = next((d for d in target_dates if d in fname), None)
        if matched_date is None:
            continue

        try:
            try:
                df = pd.read_csv(csv_path, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(csv_path, encoding="shift_jis")

            if "会場" not in df.columns:
                continue

            # 日付列があればそちらを優先
            if "日付" in df.columns:
                raw_date = str(df.iloc[0]["日付"]).strip().replace("/", "-")
                if len(raw_date) == 8 and raw_date.isdigit():
                    raw_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                if raw_date in target_dates:
                    matched_date = raw_date

            vname = str(df.iloc[0]["会場"]).strip()
            if vname not in VENUE_SLUG:
                continue

            key = (vname, matched_date)
            if key not in seen:
                seen.add(key)
                found.append(key)

        except Exception as e:
            print(f"  ⚠ CSV読込スキップ {fname}: {e}", flush=True)

    return found


# ─────────────────────────────────────────────────────────────────────────────
# メイン取得処理
# ─────────────────────────────────────────────────────────────────────────────

def fetch_history(days: int = HISTORY_DAYS,
                  dry_run: bool = False,
                  date: str | None = None,
                  date_from: str | None = None,
                  date_to: str | None = None,
                  retry: bool = False) -> None:

    # ── --retry モード：失敗リストからタスクを復元 ──────────────────────────
    if retry:
        failed_entries = load_failed_list()
        if not failed_entries:
            print("✅ 失敗リスト (failed_races.json) が空です。再取得対象なし。")
            return

        print(f"\n{'='*60}")
        print(f"  展示データ リトライ取得")
        print(f"  対象: {len(failed_entries)}レース（前回失敗分）")
        print(f"{'='*60}\n")

        tasks: list[tuple[str, str, str, int]] = []
        for entry in failed_entries:
            date_nd = entry["date"].replace("-", "")
            tasks.append((entry["venue"], entry["slug"], date_nd, entry["race"]))

        _run_tasks(tasks, dry_run)
        return

    # ── 通常モード ────────────────────────────────────────────────────────────
    target_dates = build_target_dates(
        days=days,
        date=date,
        date_from=date_from,
        date_to=date_to
    )

    print(f"\n{'='*60}")
    print(f"  展示データ一括取得")
    print(f"  対象日数/範囲: {len(target_dates)}日")
    print(f"{'='*60}\n")

    venue_dates = collect_venue_dates(target_dates)

    if not venue_dates:
        print("⚠ 対象となるCSVが見つかりませんでした。")
        print(f"  確認先: {CSV_DIR}")
        return

    # 日付の新しい順にソート
    venue_dates.sort(key=lambda x: x[1], reverse=True)

    # タスク一覧を作成（会場×日付×R1〜R12）
    tasks: list[tuple[str, str, str, int]] = []
    for venue_name, date_str in venue_dates:
        slug    = VENUE_SLUG[venue_name]
        date_nd = date_str.replace("-", "")   # YYYYMMDD
        for rno in range(1, 13):
            tasks.append((venue_name, slug, date_nd, rno))

    total = len(tasks)
    print(f"対象: {len(venue_dates)}会場×日付 / {total}レース分\n")

    _run_tasks(tasks, dry_run)


# ─────────────────────────────────────────────────────────────────────────────
# タスクリスト実行（通常・リトライ共通）
# ─────────────────────────────────────────────────────────────────────────────

def _run_tasks(tasks: list[tuple[str, str, str, int]], dry_run: bool) -> None:
    """
    (venue_name, slug, date_nd, rno) のリストを受け取って順次取得する。
    取得失敗・データなしは failed_races.json に記録。
    成功したレースは failed_races.json から削除する。
    """
    total = len(tasks)

    if dry_run:
        print("【dry-run モード: 取得は行いません】\n")
        current_date = None
        for venue_name, slug, date_nd, rno in tasks:
            d = f"{date_nd[:4]}-{date_nd[4:6]}-{date_nd[6:]}"
            if d != current_date:
                print(f"  ── {d} ──")
                current_date = d
            json_exists = (TENJI_DIR / f"tenji_{slug}_{date_nd}_R{rno:02d}.json").exists()
            mark = "✅ 取得済" if json_exists else "  未取得"
            print(f"    {mark}  {venue_name} R{rno:02d}  → tenji_{slug}_{date_nd}_R{rno:02d}.json")
        print(f"\n合計: {total}レース")
        return

    TENJI_DIR.mkdir(exist_ok=True)

    # 失敗リストを読み込み（既存分とマージするため）
    failed_list = load_failed_list()

    done       = 0
    error      = 0
    start_time = datetime.now()

    # 「会場slug × 日付」でグループ化
    def group_key(t):
        return (t[1], t[2])   # (slug, date_nd)

    tasks_sorted = sorted(tasks, key=group_key)

    for (slug, date_nd), group_iter in groupby(tasks_sorted, key=group_key):
        group = list(group_iter)
        venue_name = group[0][0]
        date_str   = f"{date_nd[:4]}-{date_nd[4:6]}-{date_nd[6:]}"   # YYYY-MM-DD

        print(f"\n{'─'*60}")
        print(f"  {venue_name}  {date_str}  ({len(group)}R)")
        print(f"{'─'*60}")

        # 1会場1日をまとめてブラウザ1インスタンスで処理
        with BrowserSession() as session:
            for venue_name_inner, slug_inner, date_nd_inner, rno in group:
                done += 1
                eta_str = _calc_eta(start_time, done, total)
                print(
                    f"\n[{done:>4}/{total}] {venue_name_inner} {date_str} R{rno:02d}"
                    f"  {eta_str}",
                    flush=True,
                )

                try:
                    rows = fetch_one(
                        venue_slug=slug_inner,
                        date=date_str,
                        race=rno,
                        out_dir=TENJI_DIR,
                        session=session,
                    )

                    if rows:
                        # 成功 → 失敗リストから除去
                        remove_succeeded(failed_list, slug_inner, date_str, rno)
                        fpath = TENJI_DIR / f"tenji_{slug_inner}_{date_nd_inner}_R{rno:02d}.json"
                        print(f"  ✅ 保存: {fpath.name}", flush=True)
                    else:
                        # データなし（サイト未掲載など） → 失敗リストに記録・ファイルは作らない
                        add_failed(failed_list, venue_name_inner, slug_inner,
                                   date_str, rno, "データなし")
                        error += 1
                        print(f"  ⚠ データなし → failed_races.json に記録", flush=True)

                except Exception as e:
                    add_failed(failed_list, venue_name_inner, slug_inner,
                               date_str, rno, f"例外: {e}")
                    error += 1
                    print(f"  ❌ エラー: {e} → failed_races.json に記録", flush=True)

                if len(group) > 1:
                    time.sleep(INTER_REQ_WAIT)

    # 失敗リストを保存
    if failed_list:
        save_failed_list(failed_list)
    else:
        # 全件成功 → 失敗リストファイルを削除
        path = TENJI_DIR / FAILED_LIST
        if path.exists():
            path.unlink()
            print(f"\n  ✅ 全件成功 → {FAILED_LIST} を削除しました", flush=True)

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n{'='*60}")
    print(f"  完了: {total}レース  エラー/空: {error}件  経過時間: {elapsed/60:.1f}分")
    if error:
        print(f"  ※ 失敗分は python fetch_tenji_history.py --retry で再取得できます")
    print(f"{'='*60}\n")


def _calc_eta(start: datetime, done: int, total: int) -> str:
    """残り時間の目安を返す"""
    if done <= 1:
        return ""
    elapsed = (datetime.now() - start).total_seconds()
    per_task = elapsed / done
    remaining = per_task * (total - done)
    h, m = divmod(int(remaining), 3600)
    m, s = divmod(m, 60)
    if h > 0:
        return f"(残 約{h}h{m:02d}m)"
    return f"(残 約{m}m{s:02d}s)"


# ─────────────────────────────────────────────────────────────────────────────
# エントリポイント（対話モード対応）
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="展示データを一括取得して tenji_data/ に保存する",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--from", dest="date_from", type=str, default=None)
    parser.add_argument("--to", dest="date_to", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retry", action="store_true",
                        help="failed_races.json の失敗分のみ再取得する")

    args = parser.parse_args()

    # --retry 指定時は日付系引数・対話モード不要
    if args.retry:
        fetch_history(retry=True, dry_run=args.dry_run)
        sys.exit(0)

    # 引数が無い場合は対話入力モード
    if not (args.days or args.date or args.date_from or args.date_to):
        print("\n=== 対話モード ===")
        mode = input("モード選択 (1=単日 2=範囲 3=過去N日) : ").strip()

        if mode == "1":
            args.date = input("取得日付 (YYYYMMDD or YYYY-MM-DD): ").strip()

        elif mode == "2":
            args.date_from = input("開始日付 (YYYYMMDD or YYYY-MM-DD): ").strip()
            args.date_to   = input("終了日付 (YYYYMMDD or YYYY-MM-DD): ").strip()

        elif mode == "3":
            args.days = int(input("過去何日分取得しますか？: ").strip())

        else:
            print("❌ 無効な入力です")
            sys.exit(1)

        dry = input("dry-runにしますか？ (y/n): ").strip().lower()
        if dry == "y":
            args.dry_run = True

    # 入力チェック
    if args.date and (args.date_from or args.date_to):
        print("❌ --date と --from/--to は同時に使えません")
        sys.exit(1)

    if (args.date_from and not args.date_to) or (args.date_to and not args.date_from):
        print("❌ --from と --to はセットで指定してください")
        sys.exit(1)

    fetch_history(
        days=args.days if args.days else HISTORY_DAYS,
        dry_run=args.dry_run,
        date=args.date,
        date_from=args.date_from,
        date_to=args.date_to,
        retry=False,
    )