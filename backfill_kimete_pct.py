# -*- coding: utf-8 -*-
"""
backfill_kimete_pct.py  ─  蓄積CSV 決まり手%列 過去分補完スクリプト

【概要】
  数値蓄積フォルダ内の全CSVに対して、以下の列が空の行を
  ボートリサーチ_マスタ.xlsx の「コース別マスタ」シートから補完する。

    逃げ%, 差し%, まくり%, まくり差し%, 抜き%   ← 攻撃決まり手
    差され%, まくられ%, まくり差され%             ← 1号艇被攻撃

【使い方】
  cd データ収集
  python scripts/backfill_kimete_pct.py
  python scripts/backfill_kimete_pct.py --force   # 既存値も上書き
"""

import argparse
import pathlib
import shutil
import sys

import pandas as pd

# ── パス設定 ──────────────────────────────────────────────────────────────
CHIKUSEKI_DIR = pathlib.Path(r"C:\Users\user\Desktop\データ収集\scripts\数値蓄積")

# 補完対象の列（CSV列名, コース別マスタのキー名）
KIMETE_COLS = [
    ("逃げ%",        "逃げ%"),
    ("差し%",        "差し%"),
    ("まくり%",      "まくり%"),
    ("まくり差し%",  "まくり差し%"),
    ("抜き%",        "抜き%"),
    ("差され%",      "差され%"),
    ("まくられ%",    "捲られ%"),
    ("まくり差され%","捲り差され%"),
]
TARGET_CSV_COLS = [col for col, _ in KIMETE_COLS]


def load_course_master():
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from lr_masters import load_masters
    from lr_config import MASTER_FILE
    import openpyxl

    if not pathlib.Path(MASTER_FILE).exists():
        raise FileNotFoundError(f"マスタExcelが見つかりません: {MASTER_FILE}")

    wb = openpyxl.load_workbook(MASTER_FILE, read_only=True, data_only=True)
    result = load_masters(wb, "一般")
    course_master = result[0]
    wb.close()
    print(f"  ✓ コース別マスタ読込: {len(course_master)}件")
    return course_master


def build_lookup(course_master) -> dict:
    """
    course_master のキーは (選手名文字列, コース文字列) 形式。
    → (選手名, コース整数) → {逃げ%: ..., 差し%: ..., ...} に変換
    """
    lookup = {}
    seen_keys = set()

    for key, cm in course_master.items():
        if not isinstance(key, tuple) or len(key) < 2:
            continue
        name_key   = str(key[0]).strip()
        course_key = str(key[1]).strip()

        try:
            course_int = int(course_key)
        except (ValueError, TypeError):
            continue

        pair = (name_key, course_int)
        if pair in seen_keys:
            continue
        seen_keys.add(pair)

        if not isinstance(cm, dict):
            continue

        row_vals = {}
        for csv_col, cm_key in KIMETE_COLS:
            v = cm.get(cm_key)
            if v is None:
                row_vals[csv_col] = ""
            else:
                try:
                    f = float(v)
                    row_vals[csv_col] = f"{f:.4f}".rstrip("0").rstrip(".")
                except (TypeError, ValueError):
                    row_vals[csv_col] = str(v).strip()

        lookup[pair] = row_vals

    print(f"  ✓ ルックアップ構築: {len(lookup)}件（選手×コース）")
    return lookup


def _is_empty(val) -> bool:
    if val is None:
        return True
    s = str(val).strip()
    return s == "" or s == "-" or s.lower() == "nan"


def backfill_csv(csv_path: pathlib.Path, lookup: dict, force: bool = False) -> int:
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str)
    except Exception as e:
        print(f"  ⚠ 読み込み失敗: {csv_path.name} ({e})")
        return 0

    if "選手名" not in df.columns or "進入コース" not in df.columns:
        print(f"  ⚠ 必須列なし: {csv_path.name}")
        return 0

    # 対象列が存在しない場合は空列として追加
    for col in TARGET_CSV_COLS:
        if col not in df.columns:
            df[col] = ""

    if force:
        target_mask = pd.Series([True] * len(df))
    else:
        empty_mask = df[TARGET_CSV_COLS].apply(
            lambda col: col.map(_is_empty)
        ).all(axis=1)
        target_mask = empty_mask

    if target_mask.sum() == 0:
        print(f"  → 補完対象なし: {csv_path.name}")
        return 0

    filled = 0
    for idx in df[target_mask].index:
        name = str(df.at[idx, "選手名"]).strip()
        try:
            course = int(float(df.at[idx, "進入コース"]))
        except (ValueError, TypeError):
            continue

        # フルネーム → 先頭4文字の順で検索
        vals = lookup.get((name, course))
        if vals is None and len(name) >= 5:
            vals = lookup.get((name[:4], course))
        if vals is None:
            continue

        for csv_col, _ in KIMETE_COLS:
            df.at[idx, csv_col] = vals.get(csv_col, "")
        filled += 1

    if filled == 0:
        print(f"  → マッチなし: {csv_path.name}")
        return 0

    bak = csv_path.with_suffix(".bak.csv")
    shutil.copy2(csv_path, bak)
    df.to_csv(csv_path, encoding="utf-8-sig", index=False)
    print(f"  ✓ {csv_path.name}: {filled}行 補完  (bak: {bak.name})")
    return filled


def main():
    parser = argparse.ArgumentParser(description="蓄積CSV 決まり手%列 過去分補完スクリプト")
    parser.add_argument("--chikuseki-dir", type=str, default=str(CHIKUSEKI_DIR))
    parser.add_argument("--force", action="store_true", help="既に値がある行も上書き")
    parser.add_argument("--dry-run", action="store_true", help="対象行数だけ確認")
    args = parser.parse_args()

    chikuseki_dir = pathlib.Path(args.chikuseki_dir)

    print("=" * 60)
    print("  蓄積CSV 決まり手%列 補完スクリプト")
    print("=" * 60)

    print(f"\n[1/2] コース別マスタを読み込み中...")
    try:
        course_master = load_course_master()
        lookup = build_lookup(course_master)
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"\n[NG] {e}")
        sys.exit(1)

    if not lookup:
        print("\n[NG] ルックアップが空です。マスタを確認してください。")
        sys.exit(1)

    print(f"\n[2/2] 蓄積CSVを補完中...")
    print(f"      対象フォルダ: {chikuseki_dir}")

    if not chikuseki_dir.exists():
        print(f"\n[NG] フォルダが見つかりません: {chikuseki_dir}")
        sys.exit(1)

    csv_files = sorted([
        f for f in chikuseki_dir.glob("*.csv")
        if not f.name.endswith(".bak.csv")
    ])

    if not csv_files:
        print("  [!] 補完対象のCSVが見つかりません。")
        sys.exit(0)

    print(f"  対象ファイル: {len(csv_files)} 件")

    total_filled = 0
    for csv_path in csv_files:
        if args.dry_run:
            try:
                df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str)
                cols = [c for c in TARGET_CSV_COLS if c in df.columns]
                n = df[cols].apply(lambda c: c.map(_is_empty)).all(axis=1).sum() if cols else len(df)
                print(f"  {csv_path.name}: 補完対象 {n}行")
                total_filled += n
            except Exception as e:
                print(f"  ⚠ {csv_path.name}: {e}")
        else:
            total_filled += backfill_csv(csv_path, lookup, force=args.force)

    print()
    print("=" * 60)
    if args.dry_run:
        print(f"  [DRY-RUN] 補完予定: {total_filled}行")
    else:
        print(f"  [完了] 補完: {total_filled}行")
        if total_filled > 0:
            print("  ※ 元ファイルは .bak.csv としてバックアップ済み")
    print("=" * 60)


if __name__ == "__main__":
    main()
