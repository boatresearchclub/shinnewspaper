# -*- coding: utf-8 -*-
"""
recalc_indices.py  ─  指数並列再計算スクリプト

【用途】
  指数ロジック改良後、数値蓄積フォルダの pkl を全件 or 指定会場だけ高速再計算する。
  load_race.py --collect の処理を「日付×会場」単位で並列化したもの。

【使い方】
  # 全会場・全日付を再計算
  python recalc_indices.py

  # 特定会場だけ再計算
  python recalc_indices.py --venue びわこ
  python recalc_indices.py --venue びわこ 常滑 宮島

  # 並列数を指定（デフォルト: CPUコア数）
  python recalc_indices.py --workers 4

  # 強制再計算（既存pklを無視して全件上書き）
  python recalc_indices.py --force

【速度の目安】
  直列（旧 load_race.py --collect）: 例 53日×1会場 ≈ 数分
  並列（本スクリプト）             : CPUコア数倍速
"""

import glob
import os
import pathlib
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count

# ── パス設定 ────────────────────────────────────────────────────────────────
_SCRIPT_DIR    = pathlib.Path(__file__).parent
_CHIKUSEKI_DIR = pathlib.Path(r"C:\Users\user\Desktop\データ収集\scripts\数値蓄積")

sys.path.insert(0, str(_SCRIPT_DIR))

# ── インポート ───────────────────────────────────────────────────────────────
from lr_config import MASTER_FILE, CSV_DIR
from lr_masters import load_masters, load_csv, load_motor_csv
from lr_calc import calc_race_indices
from openpyxl import load_workbook

try:
    from evaluate_jizen import evaluate_all_with_scores
    JIZEN_AVAILABLE = True
except ImportError:
    JIZEN_AVAILABLE = False

try:
    from lr_suggest import build_jizen_members
    SUGGEST_AVAILABLE = True
except ImportError:
    SUGGEST_AVAILABLE = False

try:
    from export_indices_csv import overwrite_venue_all, get_existing_keys
    INDICES_AVAILABLE = True
except ImportError:
    INDICES_AVAILABLE = False
    print("[!] export_indices_csv.py が見つかりません")


# ════════════════════════════════════════════════════════════════════════════
# マスタをプロセス間で共有するためのグローバルキャッシュ
# （ProcessPoolExecutor では initializer で各ワーカーに持たせる）
# ════════════════════════════════════════════════════════════════════════════

_MASTERS = None  # ワーカープロセス内のみ使用


def _init_worker():
    """各ワーカープロセスの初期化：マスタを一度だけ読み込む"""
    global _MASTERS
    try:
        wb = load_workbook(str(MASTER_FILE), read_only=True, data_only=True)
        (course_master, player_master, ininage_master, venue_stats_master,
         venue_course_master, tenkai_venue_master, tenkai_national_master,
         st_kimete_master, kaiho_venue_master, kaiho_national_master,
         effective_grade) = load_masters(wb, "一般")
        wb.close()
        _MASTERS = dict(
            course_master=course_master,
            player_master=player_master,
            ininage_master=ininage_master,
            venue_stats_master=venue_stats_master,
            venue_course_master=venue_course_master,
            tenkai_venue_master=tenkai_venue_master,
            tenkai_national_master=tenkai_national_master,
            st_kimete_master=st_kimete_master,
            kaiho_venue_master=kaiho_venue_master,
            kaiho_national_master=kaiho_national_master,
            effective_grade=effective_grade,
        )
    except Exception as e:
        print(f"[NG] ワーカー初期化失敗: {e}")
        _MASTERS = None


# ════════════════════════════════════════════════════════════════════════════
# 1タスク = 1日付 × 1会場
# ════════════════════════════════════════════════════════════════════════════

def _process_one(task: tuple) -> dict:
    """
    1日付×1会場分の指数を計算して race_data リストを返す。
    ProcessPoolExecutor のワーカーで実行される。

    Returns:
        {"venue": str, "date": str, "rows": int, "skipped": bool, "error": str|None}
    """
    venue, proc_date, chikuseki_dir, force = task

    if _MASTERS is None:
        return {"venue": venue, "date": proc_date, "rows": 0,
                "skipped": False, "error": "マスタ未初期化"}

    m = _MASTERS

    # ── 重複チェック（--force でない場合）──────────────────────────────────
    if not force and INDICES_AVAILABLE:
        try:
            pkl_out = pathlib.Path(chikuseki_dir) / f"{venue}.pkl"
            existing = get_existing_keys(pkl_out)
            if (proc_date, venue, "1", "1") in existing:
                return {"venue": venue, "date": proc_date, "rows": 0,
                        "skipped": True, "error": None}
        except Exception:
            pass

    # ── CSV読み込み ─────────────────────────────────────────────────────────
    try:
        df, race_date = load_csv(venue, None, proc_date)
    except Exception as e:
        return {"venue": venue, "date": proc_date, "rows": 0,
                "skipped": False, "error": f"CSV読み込み失敗: {e}"}

    if df is None or len(df) == 0:
        return {"venue": venue, "date": proc_date, "rows": 0,
                "skipped": False, "error": "CSVなし"}

    try:
        motor_df = load_motor_csv(venue, None, race_df=df) if JIZEN_AVAILABLE else None
    except Exception:
        motor_df = None

    race_col = next((c for c in df.columns if "レース" in c or c == "R"), None)
    race_nos = (
        sorted(df[race_col].unique(), key=lambda x: int(x) if str(x).isdigit() else 99)
        if race_col else ["1"]
    )

    # ── レースごとに指数計算 ────────────────────────────────────────────────
    all_race_data = []
    for race_no in race_nos:
        if race_col:
            race_df = df[df[race_col].astype(str) == str(race_no)]
        else:
            race_df = df
        players = [dict(row) for _, row in race_df.iterrows()]
        if not players:
            continue

        # 指数計算
        try:
            results, slit, venue_stats, frame_2nd, race_judgment, bet_suggestions = calc_race_indices(
                venue, race_no, players,
                m["course_master"], m["player_master"], m["ininage_master"],
                m["venue_stats_master"], m["venue_course_master"],
                tenkai_venue_master=m["tenkai_venue_master"],
                tenkai_national_master=m["tenkai_national_master"],
                st_kimete_master=m["st_kimete_master"],
                kaiho_venue_master=m["kaiho_venue_master"],
                kaiho_national_master=m["kaiho_national_master"],
                race_grade=m["effective_grade"],
            )
        except Exception as e:
            continue  # 1レース失敗は無視して続行

        # 事前評価
        jizen_eval_result = None
        if JIZEN_AVAILABLE and SUGGEST_AVAILABLE:
            try:
                jizen_members = build_jizen_members(
                    results, m["course_master"], m["player_master"], motor_df, race_no
                )
                if jizen_members:
                    jizen_eval_result = evaluate_all_with_scores(jizen_members)
            except Exception:
                pass

        all_race_data.append({
            "race_no":       race_no,
            "venue":         venue,
            "race_date":     race_date,
            "results":       results,
            "jizen_eval":    jizen_eval_result,
            "race_judgment": race_judgment,
        })

    if not all_race_data:
        return {"venue": venue, "date": proc_date, "rows": 0,
                "skipped": False, "error": "有効データなし"}

    # ── pkl 上書き保存 ──────────────────────────────────────────────────────
    if INDICES_AVAILABLE:
        try:
            pkl_out = pathlib.Path(chikuseki_dir) / f"{venue}.pkl"
            from export_indices_csv import append_all_races
            append_all_races(all_race_data, output_path=pkl_out)
        except Exception as e:
            return {"venue": venue, "date": proc_date,
                    "rows": len(all_race_data), "skipped": False,
                    "error": f"pkl保存失敗: {e}"}

    return {"venue": venue, "date": proc_date,
            "rows": len(all_race_data), "skipped": False, "error": None}


# ════════════════════════════════════════════════════════════════════════════
# タスクリスト生成
# ════════════════════════════════════════════════════════════════════════════

def _collect_tasks(venues: list, chikuseki_dir: pathlib.Path, force: bool) -> list:
    """(venue, date, chikuseki_dir, force) のタスクリストを生成"""
    tasks = []
    seen = set()
    for venue in venues:
        files = (
            sorted(glob.glob(str(CSV_DIR / f"{venue}_*.csv"))) +
            sorted(glob.glob(str(CSV_DIR / venue / f"{venue}_*.csv")))
        )
        for f in files:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(f))
            if m:
                key = (venue, m.group(1))
                if key not in seen:
                    tasks.append((venue, m.group(1), str(chikuseki_dir), force))
                    seen.add(key)
    return sorted(tasks, key=lambda t: (t[1], t[0]))  # 日付→会場順


# ════════════════════════════════════════════════════════════════════════════
# メイン
# ════════════════════════════════════════════════════════════════════════════

def _sep(c="="):
    print("  " + c * 54)


def _collect_all_venues() -> list:
    """csv_output から会場リストを収集"""
    seen_v, venues = set(), []
    all_files = (
        sorted(glob.glob(str(CSV_DIR / "*.csv"))) +
        sorted(glob.glob(str(CSV_DIR / "**" / "*.csv"), recursive=True))
    )
    for f in all_files:
        if not re.search(r"\d{4}-\d{2}-\d{2}", os.path.basename(f)):
            continue
        parts = pathlib.Path(f).relative_to(CSV_DIR).parts
        v = parts[0] if len(parts) >= 2 else os.path.basename(f).split("_")[0]
        if v and v not in seen_v:
            venues.append(v)
            seen_v.add(v)
    return venues


def main():
    _sep()
    print("  指数並列再計算スクリプト")
    _sep()

    # ── 数値蓄積フォルダ確認 ─────────────────────────────────────────────────
    if not _CHIKUSEKI_DIR.exists():
        print(f"  [NG] 数値蓄積フォルダが見つかりません: {_CHIKUSEKI_DIR}")
        return

    # ── 会場リスト収集 ───────────────────────────────────────────────────────
    all_venues = _collect_all_venues()
    if not all_venues:
        print("  [NG] 対象会場が見つかりません。csv_output/ にCSVを置いてください。")
        return

    # ════════════════════════════════════════════════════════════════════
    # ① 会場選択
    # ════════════════════════════════════════════════════════════════════
    print()
    print("  ┌──────────────────────────────────────────────┐")
    print("  │  対象会場を選択してください                    │")
    print("  └──────────────────────────────────────────────┘")
    print("    0. 全会場（一括処理）")
    for i, v in enumerate(all_venues, 1):
        print(f"    {i}. {v}")

    while True:
        sel = input(f"\n  番号を入力 (0=全会場, 1〜{len(all_venues)}): ").strip()
        if sel == "0":
            venues = all_venues
            print(f"  ✓ 全会場: {', '.join(venues)}")
            break
        if sel.isdigit() and 1 <= int(sel) <= len(all_venues):
            venues = [all_venues[int(sel) - 1]]
            print(f"  ✓ 会場: {venues[0]}")
            break
        print("  [!] 正しい番号を入力してください")

    # ════════════════════════════════════════════════════════════════════
    # ② 再計算モード選択
    # ════════════════════════════════════════════════════════════════════
    print()
    print("  ┌──────────────────────────────────────────────┐")
    print("  │  再計算モードを選択してください                │")
    print("  └──────────────────────────────────────────────┘")
    print("    1. 差分のみ（既存pklにない日付だけ追加）")
    print("    2. 全件強制（既存pklを全て上書き）")

    while True:
        sel = input("\n  番号を入力 (1 or 2, Enter=1): ").strip()
        if sel in ("", "1"):
            force = False
            print("  ✓ モード: 差分のみ")
            break
        if sel == "2":
            force = True
            print("  ✓ モード: 全件強制再計算")
            break
        print("  [!] 1 か 2 を入力してください")

    # ════════════════════════════════════════════════════════════════════
    # ③ 並列数選択
    # ════════════════════════════════════════════════════════════════════
    n_cores = cpu_count()
    print()
    print("  ┌──────────────────────────────────────────────┐")
    print("  │  並列数を選択してください                      │")
    print("  └──────────────────────────────────────────────┘")
    print(f"    Enter = 自動（CPUコア数: {n_cores}）")
    print(f"    数字  = 任意（例: 4）")

    while True:
        sel = input(f"\n  並列数を入力 (Enter={n_cores}): ").strip()
        if sel == "":
            n_workers = n_cores
            print(f"  ✓ 並列数: {n_workers}")
            break
        if sel.isdigit() and int(sel) >= 1:
            n_workers = int(sel)
            print(f"  ✓ 並列数: {n_workers}")
            break
        print("  [!] 1 以上の数字を入力してください")

    # ── タスク生成 ───────────────────────────────────────────────────────────
    tasks = _collect_tasks(venues, _CHIKUSEKI_DIR, force)
    if not tasks:
        print()
        print("  [!] 処理対象タスクがありません（全て既存pklに存在）。")
        print("      全件再計算する場合はモード 2 を選択してください。")
        return

    # ── 実行確認 ─────────────────────────────────────────────────────────────
    print()
    _sep("-")
    print(f"  対象会場  : {', '.join(venues)}")
    print(f"  タスク数  : {len(tasks)}件（日付×会場）")
    print(f"  並列数    : {n_workers}ワーカー")
    print(f"  再計算    : {'全件強制' if force else '差分のみ'}")
    _sep("-")
    sel = input("\n  上記の設定で実行しますか？ (Enter=実行 / q=中止): ").strip().lower()
    if sel == "q":
        print("  中止しました。")
        return
    print()

    # ── 並列実行 ─────────────────────────────────────────────────────────────
    t_start = time.perf_counter()
    done = skipped = errors = total_rows = 0

    with ProcessPoolExecutor(
        max_workers=n_workers,
        initializer=_init_worker,
    ) as executor:
        futures = {executor.submit(_process_one, t): t for t in tasks}
        for future in as_completed(futures):
            try:
                r = future.result()
            except Exception as e:
                task = futures[future]
                print(f"  [NG] {task[0]} {task[1]}: {e}")
                errors += 1
                continue

            if r["skipped"]:
                skipped += 1
            elif r["error"] and r["rows"] == 0:
                if "CSVなし" not in r["error"]:
                    print(f"  [!]  {r['venue']} {r['date']}: {r['error']}")
                errors += 1
            else:
                done += 1
                total_rows += r["rows"]
                print(f"  [OK] {r['venue']} {r['date']}  {r['rows']}R")

    elapsed = time.perf_counter() - t_start
    print()
    _sep()
    print(f"  完了: {done}件処理  {skipped}件スキップ  {errors}件エラー")
    print(f"  合計: {total_rows}レース  経過時間: {elapsed:.1f}秒")
    _sep()


if __name__ == "__main__":
    main()
