# -*- coding: utf-8 -*-
import traceback
try:
    import pandas as pd, pathlib, glob, sys
    sys.path.insert(0, r"C:\Users\user\Desktop\データ収集\scripts")
    from backfill_kimari import build_kimari_table, pct_to_str

    raw_dir = pathlib.Path(r"C:\Users\user\Desktop\データ収集\data\raw")
    table = build_kimari_table(raw_dir)
    print(table.head(10).to_string())
    print()
    # pct_to_str の結果も確認
    for _, row in table.head(5).iterrows():
        print(pct_to_str(row), "←", dict(row))

except Exception:
    traceback.print_exc()

input("Enterキーで閉じる")