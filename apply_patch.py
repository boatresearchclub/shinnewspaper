# -*- coding: utf-8 -*-
"""
apply_patch.py  ─  load_race.py に指数CSV組み込みパッチを自動適用する

【使い方】
  python scripts/apply_patch.py

【やること】
  1. load_race.py の lr_log インポート行の直後に export_indices_csv インポートを追加
  2. write_numeric_sheet の直後に _append_indices_csv 呼び出しを追加
  3. バックアップ load_race.py.bak を作成してから書き換え
"""

import pathlib, shutil, sys

TARGET = pathlib.Path(__file__).parent / "load_race.py"
BACKUP = pathlib.Path(__file__).parent / "load_race.py.bak"

IMPORT_SEARCH = "from lr_log import _flush_prediction_log, calc_roi_from_logs"
IMPORT_INSERT = """\nfrom lr_log import _flush_prediction_log, calc_roi_from_logs

try:
    from export_indices_csv import append_all_races as _append_indices_csv
    _INDICES_CSV_AVAILABLE = True
except ImportError:
    _INDICES_CSV_AVAILABLE = False
    print('[!]  export_indices_csv.py が見つかりません。指数CSV出力はスキップされます。')"""

CALL_SEARCH = "            write_numeric_sheet(wb, all_race_data, course_master, venue_course_master)"
CALL_INSERT  = """\
            write_numeric_sheet(wb, all_race_data, course_master, venue_course_master)

        # ── 指数CSV蓄積 ────────────────────────────────────────────────
        if all_race_data and _INDICES_CSV_AVAILABLE:
            try:
                _append_indices_csv(all_race_data)
            except Exception as _csv_e:
                print(f'  [!]  指数CSV出力エラー（続行します）: {_csv_e}')
        # ────────────────────────────────────────────────────────────────"""

def main():
    if not TARGET.exists():
        print(f"[NG] load_race.py が見つかりません: {TARGET}")
        sys.exit(1)

    src = TARGET.read_text(encoding="utf-8")

    # ── 既適用チェック ────────────────────────────────────────────────
    if "_INDICES_CSV_AVAILABLE" in src:
        print("[OK] パッチは既に適用済みです。何もしません。")
        sys.exit(0)

    # ── バックアップ ──────────────────────────────────────────────────
    shutil.copy2(str(TARGET), str(BACKUP))
    print(f"[BAK] バックアップ作成: {BACKUP.name}")

    # ── パッチ① インポート追加 ────────────────────────────────────────
    if IMPORT_SEARCH not in src:
        print(f"[NG] インポート挿入箇所が見つかりません。手動で適用してください。")
        print(f"     検索文字列: {IMPORT_SEARCH!r}")
        sys.exit(1)

    src = src.replace(IMPORT_SEARCH, IMPORT_INSERT, 1)
    print("[OK] パッチ① インポート追加 完了")

    # ── パッチ② 呼び出し追加 ─────────────────────────────────────────
    if CALL_SEARCH not in src:
        print(f"[NG] 呼び出し挿入箇所が見つかりません。手動で適用してください。")
        print(f"     検索文字列: {CALL_SEARCH!r}")
        sys.exit(1)

    src = src.replace(CALL_SEARCH, CALL_INSERT, 1)
    print("[OK] パッチ② 呼び出し追加 完了")

    # ── 書き込み ──────────────────────────────────────────────────────
    TARGET.write_text(src, encoding="utf-8")
    print(f"[OK] {TARGET.name} を更新しました")
    print()
    print("  次回から load_race.py を起動すると")
    print("  csv_output/indices_log.csv に指数が自動蓄積されます。")

if __name__ == "__main__":
    main()
