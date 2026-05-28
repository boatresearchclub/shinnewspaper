# -*- coding: utf-8 -*-
"""
convert_all_pkl.py  ─  数値蓄積フォルダの全pkl→CSV一括変換

使い方:
  python convert_all_pkl.py
"""

import pathlib
import pandas as pd

CHIKUSEKI_DIR = pathlib.Path(r"C:\Users\user\Desktop\データ収集\scripts\数値蓄積")

def main():
    pkl_files = sorted(CHIKUSEKI_DIR.glob("*.pkl"))
    if not pkl_files:
        print(f"[!] pklファイルが見つかりません: {CHIKUSEKI_DIR}")
        return

    print(f"対象: {len(pkl_files)}会場")
    print("-" * 40)

    for pkl in pkl_files:
        try:
            df = pd.read_pickle(pkl)
            csv_path = pkl.with_suffix(".csv")
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"[OK] {pkl.stem}  {len(df)}行 → {csv_path.name}")
        except Exception as e:
            print(f"[NG] {pkl.stem}: {e}")

    print("-" * 40)
    print("完了")

if __name__ == "__main__":
    main()
