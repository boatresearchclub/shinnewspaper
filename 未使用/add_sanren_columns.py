# -*- coding: utf-8 -*-
"""
add_sanren_columns.py
─────────────────────
数値蓄積フォルダ内の全会場CSVに
「3連対指数」「3連対補正比」列を追加する（既存データは空欄）。

【使い方】
    python add_sanren_columns.py

【動作】
    - C:\\Users\\user\\Desktop\\データ収集\\scripts\\数値蓄積\\ 内の全 .csv を対象
    - 既に「3連対指数」列があるファイルはスキップ
    - 挿入位置: 「会場別信頼度」列の直後
    - 元ファイルは .bak として自動バックアップ
"""

import csv
import pathlib
import shutil

CHIKUSEKI_DIR = pathlib.Path(r"C:\Users\user\Desktop\データ収集\scripts\数値蓄積")

# 挿入する列名（会場別信頼度の直後）
INSERT_AFTER = "会場別信頼度"
NEW_COLS     = ["3連対指数", "3連対補正比"]


def add_columns(csv_path: pathlib.Path):
    # 読み込み
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
        f.seek(0)
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])

    # 既に追加済みならスキップ
    if NEW_COLS[0] in headers:
        print(f"  [SKIP] {csv_path.name} （既に列あり）")
        return

    # バックアップ
    bak = csv_path.with_suffix(".bak.csv")
    shutil.copy2(csv_path, bak)

    # 挿入位置を決定（INSERT_AFTER の直後、なければ末尾）
    if INSERT_AFTER in headers:
        pos = headers.index(INSERT_AFTER) + 1
    else:
        pos = len(headers)

    new_headers = headers[:pos] + NEW_COLS + headers[pos:]

    # 書き込み（新列は空欄）
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=new_headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            for col in NEW_COLS:
                row.setdefault(col, "")
            writer.writerow(row)

    print(f"  [OK]  {csv_path.name} → 列追加完了（{len(rows)}行）")


def main():
    if not CHIKUSEKI_DIR.exists():
        print(f"[NG] フォルダが見つかりません: {CHIKUSEKI_DIR}")
        return

    csv_files = sorted(CHIKUSEKI_DIR.glob("*.csv"))
    if not csv_files:
        print("[NG] CSVファイルが見つかりません")
        return

    print(f"対象: {len(csv_files)}ファイル")
    print(f"追加列: {NEW_COLS}（挿入位置: 「{INSERT_AFTER}」の直後）")
    print()

    for p in csv_files:
        add_columns(p)

    print()
    print("完了。元ファイルは .bak.csv としてバックアップ済みです。")


if __name__ == "__main__":
    main()
